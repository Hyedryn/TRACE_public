"""Modern LLM service integrations with structured output using LangChain."""
import json
import logging
from typing import List, Any, Literal
from pydantic import BaseModel, Field, create_model

from langchain_openai import ChatOpenAI, AzureChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

from config import get_config
from models import (
    VideoRecommendation, 
    RecommendationsList, 
    VideoChoice, 
    RelevanceCheck,
    LLMError,
    UnsupportedProviderError
)

logger = logging.getLogger(__name__)


def validate_provider(provider: str) -> None:
    """Validate that the provider supports structured output."""
    supported_providers = ["openai", "azure_openai", "openrouter"]
    if provider not in supported_providers:
        raise UnsupportedProviderError(
            f"Provider '{provider}' is not supported. "
            f"Supported providers: {', '.join(supported_providers)}"
        )


def get_langchain_llm(provider: str, model: str) -> ChatOpenAI:
    """Get the appropriate LangChain LLM based on provider."""
    config = get_config()

    if provider == "azure_openai":
        api_key = config.get_api_key("azure_openai")
        endpoint = getattr(config.api_keys, 'azure_openai_endpoint', None)
        if not api_key or not endpoint:
            raise LLMError("Azure OpenAI credentials not configured")
        return AzureChatOpenAI(
            api_key=api_key,
            api_version="2025-04-01-preview",
            azure_endpoint=endpoint,
            model=model,
            temperature=0.1
        )
    if provider == "openai":
        api_key = config.get_api_key("openai")
        if not api_key:
            raise LLMError("OpenAI API key not configured")
        return ChatOpenAI(
            api_key=api_key,
            model=model,
            temperature=0.1
        )
    if provider == "openrouter":
        api_key = config.get_api_key("openrouter")
        if not api_key:
            raise LLMError("OpenRouter API key not configured")
        return ChatOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
            model=model,
            temperature=0.1
        )

    raise UnsupportedProviderError(
        f"LangChain client not available for {provider}"
    )

def call_llm_structured(
    provider: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    response_model: BaseModel
) -> Any:
    """
    Call LLM with structured output using LangChain.

    Args:
        provider: LLM provider name
        model: Model name
        system_prompt: System message
        user_prompt: User message
        response_model: Pydantic model for response structure

    Returns:
        Parsed response as Pydantic model instance
    """
    validate_provider(provider)
    logger.info("Calling %s with model %s", provider, model)

    try:
        # Get LangChain LLM
        llm = get_langchain_llm(provider, model)
        llm_structured = llm.with_structured_output(response_model, method="json_schema")

        # Create prompt template
        prompt = ChatPromptTemplate.from_messages([
            ("system", "{system_prompt}"),
            ("human", "{user_prompt}")
        ])

        # Create chain
        chain = prompt | llm_structured

        # Execute chain
        response = chain.invoke({
            "system_prompt": system_prompt,
            "user_prompt": user_prompt
        })

        logger.debug("[call_llm_structured] response: %s", response)

        if not response:
            raise LLMError("Empty response from LLM")

        return response

    except Exception as e:
        logger.error("LLM call failed: %s", e)
        if isinstance(e, (LLMError, UnsupportedProviderError)):
            raise
        raise LLMError(f"LLM call failed: {e}") from e


def parse_recommendations_with_llm(
    provider: str,
    model: str,
    recommendations_html_list: List[str]
) -> RecommendationsList:
    """Parse video recommendations using LLM with structured output."""

    system_prompt = """You are a highly intelligent data extraction engine. Your sole purpose is to parse raw HTML from YouTube and convert it into a structured, clean format.

**Rules:**
1. Extract video information from HTML blocks
2. Convert view counts to integers (e.g., "1.2M views" -> 1200000)
3. Extract video_id from href attributes
4. Construct full YouTube URLs
5. Format duration as h:mm:ss or mm:ss
6. Ignore ads and blocks without complete information
7. Only include videos with all required fields

**Critical:** Only return videos that have all required information: title, publisher, views, video_id, link, and duration."""

    user_prompt = (
        f"Parse these YouTube recommendation HTML blocks:\n\n"
        f"{json.dumps(recommendations_html_list)}"
    )

    try:
        result = call_llm_structured(
            provider=provider,
            model=model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_model=RecommendationsList
        )

        logger.info("Successfully parsed %d recommendations", len(result.recommendations))
        return result

    except Exception as e:
        logger.error("Failed to parse recommendations: %s", e)
        raise LLMError(f"Failed to parse recommendations: {e}") from e


def choose_video_with_llm(
    provider: str,
    model: str,
    persona_description: str,
    recommendations: RecommendationsList
) -> VideoChoice:
    """Choose a video based on persona using structured output."""

    if not recommendations.recommendations:
        raise LLMError("No recommendations provided for video selection")

    # Extract video IDs from recommendations
    video_ids = [rec.video_id for rec in recommendations.recommendations]
    
    # Create a dynamic Literal type using exec to construct it properly
    literal_args = ', '.join(repr(vid) for vid in video_ids) + ', ' + repr("no_interesting_video")
    literal_type_code = f"Literal[{literal_args}]"
    
    logger.debug("Creating dynamic Literal type with video IDs: %s", video_ids)
    logger.debug("Literal type code: %s", literal_type_code)
    
    # Create the type in a safe namespace
    namespace = {'Literal': Literal}
    exec(f"video_id_type = {literal_type_code}", namespace)
    video_id_type = namespace['video_id_type']
    
    DynamicVideoChoice = create_model(
        'DynamicVideoChoice',
        video_id=(video_id_type, Field(
            description=f"The chosen video ID, if no interesting video are found, choose the video_id no_interesting_video."
        )),
        justification=(str, Field(description="Explanation for the choice"))
    )

    system_prompt = (
        f"You are simulating a YouTube user with the following persona:\n\n{persona_description}\n\n"
        f"Task: You are shown a list of recommended YouTube videos, each with its title and channel "
        f"name. Based on the persona’s preferences, stance, language, and personality traits, decide which "
        f"single video the persona will watch next.\n"
        f"Instructions :\n"
        f"- If one of the videos strongly matches the persona’s interests and aligns with its preferences, choose it.\n"
        f"- If multiple videos are equally relevant, pick the one that best fits the persona’s stance and viewing behavior.\n"
        f"- If none of the videos is worth watching, answer {repr('no_interesting_video')}. This will reload the homepage for new recommendations.\n\n"
        f"Provide your choice with a clear justification.\n"
    )

    # Convert Pydantic model to dict for JSON serialization
    recommendations_dict = [rec.model_dump() for rec in recommendations.recommendations]
    user_prompt = (
        f"Choose from these videos:\n\n"
        f"{json.dumps(recommendations_dict, indent=2)}"
    )

    try:
        result = call_llm_structured(
            provider=provider,
            model=model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_model=DynamicVideoChoice
        )
        
        # Convert the dynamic model result back to the standard VideoChoice model
        return VideoChoice(
            video_id=result.video_id,
            justification=result.justification
        )

    except Exception as e:
        logger.error("Failed to choose video: %s", e)
        raise LLMError(f"Failed to choose video: {e}") from e


def check_video_relevance_with_llm(
    provider: str,
    model: str,
    persona_description: str,
    transcript_text: str,
    transcript_seconds: int
) -> RelevanceCheck:
    """Check video relevance using structured output."""

    system_prompt = (
        f"You are simulating a YouTube user with the following persona:\n\n{persona_description}\n\n"
        f"Task: You have watched the first {transcript_seconds} seconds of a YouTube video. "
        f"Based on the transcript content from this time period, decide whether the persona "
        f"continues watching the video until the end or stops watching now.\n\n"
        f"- Set is_relevant to True if the content aligns with the persona’s preferences, stance, and language, "
        f"or is interesting enough to watch fully.\n"
        f"- Set is_relevant to False if the content contradicts the persona’s stance, is uninteresting, or irrelevant.\n\n"
        f"Provide your choice with a clear justification.\n"
    )

    user_prompt = f"Analyze this video transcript:\n\n{transcript_text}"

    try:
        result = call_llm_structured(
            provider=provider,
            model=model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_model=RelevanceCheck
        )
        return result

    except Exception as e:
        logger.error("Failed to check video relevance: %s", e)
        raise LLMError(f"Failed to check video relevance: {e}") from e