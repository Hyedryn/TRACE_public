"""Pydantic models for the YouTube scraper."""
from typing import List
from pydantic import BaseModel, Field


class VideoRecommendation(BaseModel):
    """Model for a single video recommendation."""
    title: str = Field(description="The video title")
    publisher: str = Field(description="The channel/publisher name")
    views: int = Field(description="Number of views as integer")
    video_id: str = Field(description="YouTube video ID")
    link: str = Field(description="Full YouTube URL")
    duration: str = Field(description="Video duration in format h:mm:ss or mm:ss")
    recommendation_source: str = Field(default="sidebar", description="Source of the recommendation: sidebar, homepage, or context")


class RecommendationsList(BaseModel):
    """Model for a list of video recommendations."""
    recommendations: List[VideoRecommendation] = Field(
        description="List of parsed video recommendations"
    )


class VideoChoice(BaseModel):
    """Model for video selection decision."""
    video_id: str = Field(description="The chosen video ID")
    justification: str = Field(description="Explanation for the choice (one or two sentences)")


class RelevanceCheck(BaseModel):
    """Model for video relevance assessment."""
    is_relevant: bool = Field(description="Whether the video is relevant to the persona")
    justification: str = Field(description="Explanation for the relevance decision (one or two sentences)")


# Custom exceptions
class LLMError(Exception):
    """Custom exception for LLM-related errors."""
    pass


class UnsupportedProviderError(LLMError):
    """Exception for unsupported LLM providers."""
    pass