"""Modern configuration system for the YouTube scraper."""
import os
import logging
import json
import yaml
import re
from pathlib import Path
from typing import Optional, List, Dict, Any, Literal
from pydantic import Field, validator, BaseModel, root_validator
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)

class LLMProviderConfig(BaseSettings):
    """Configuration for a single LLM provider."""
    provider: Literal["openai", "azure_openai", "openrouter"]
    model: str

    class Config:
        extra = "forbid"


class LLMConfig(BaseSettings):
    """LLM configuration for all tasks."""
    parse_recommendations: Optional[LLMProviderConfig] = None
    choose_video: Optional[LLMProviderConfig] = None
    check_relevance: Optional[LLMProviderConfig] = None

    class Config:
        extra = "forbid"


class APIKeysConfig(BaseSettings):
    """API keys configuration."""
    openai: Optional[str]
    azure_openai_key: Optional[str]
    azure_openai_endpoint: Optional[str]
    openrouter: Optional[str]

    class Config:
        extra = "forbid"


class ScrapingConfig(BaseSettings):
    """Scraping behavior configuration."""
    parser_method: Literal["llm", "bs"] = "bs"
    max_duration: int = 300
    max_depth: int = 5
    browser_type: Literal["chrome", "firefox"] = "chrome"

    # Persona filtering
    persona_filter_enabled: bool = False
    persona_filter_seconds: int = 60
    persona_filter_transcript_seconds: int = 120

    class Config:
        extra = "forbid"


class DatabaseConfig(BaseSettings):
    """Database configuration."""
    url: str

    class Config:
        extra = "forbid"


class SeleniumConfig(BaseSettings):
    """Selenium configuration."""
    hub_url: Optional[str]

    class Config:
        extra = "forbid"


class LoggingConfig(BaseSettings):
    """Logging configuration."""
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
    selenium_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

    class Config:
        extra = "forbid"


class PersonaMixConfig(BaseModel):
    profile_id: int
    weight: float


class PersonaSequenceConfig(BaseModel):
    profile_id: int
    steps: int


class ExperimentConfig(BaseModel):
    # Add the new context fields
    context_name: Optional[str] = None
    context_video_ids: Optional[List[str]] = None

    # Existing mode and persona fields
    mode: Literal['single_persona', 'mixed_persona', 'random_choice', 'sequential_persona']
    profile_id: Optional[int] = None
    persona_mix: Optional[List[PersonaMixConfig]] = None
    persona_sequence: Optional[List[PersonaSequenceConfig]] = None

    # Concurrent users for parallel execution
    concurrent_users: int = 1
    max_depth: Optional[int] = None

    @validator('context_video_ids', always=True)
    def check_exclusive_context(cls, v, values):
        """Ensure that only one context definition method is used."""
        if values.get('context_name') and v:
            raise ValueError("'context_name' and 'context_video_ids' are mutually exclusive. Please choose one.")
        return v

    @validator('profile_id', always=True)
    def check_profile_id_for_single_persona(cls, v, values):
        """Ensure profile_id is provided for 'single_persona' mode."""
        if values.get('mode') == 'single_persona' and v is None:
            raise ValueError("A 'profile_id' must be provided when using 'single_persona' mode.")
        return v

    @validator('persona_mix', always=True)
    def check_persona_mix(cls, v, values):
        """Ensure persona_mix is provided and valid for 'mixed_persona' mode."""
        if values.get('mode') == 'mixed_persona':
            if not v:
                raise ValueError("A 'persona_mix' list must be provided when using 'mixed_persona' mode.")

            # Check that weights sum to approximately 1.0
            total_weight = sum(p.weight for p in v)
            if not (0.99 < total_weight < 1.01):
                raise ValueError(f"The weights in 'persona_mix' must sum to 1.0 (current sum: {total_weight}).")
        return v

    @validator('persona_sequence', always=True)
    def check_persona_sequence(cls, v, values):
        """Ensure persona_sequence is provided for 'sequential_persona' mode."""
        if values.get('mode') == 'sequential_persona' and not v:
            raise ValueError("A 'persona_sequence' list must be provided when using 'sequential_persona' mode.")
        return v


class ScraperConfig(BaseSettings):
    """Main scraper configuration."""
    # Required settings
    experiment: ExperimentConfig
    database: DatabaseConfig

    # Optional settings with defaults
    llm: LLMConfig = Field(default_factory=LLMConfig)
    api_keys: APIKeysConfig = Field(default_factory=APIKeysConfig)
    scraping: ScrapingConfig = Field(default_factory=ScrapingConfig)
    selenium: SeleniumConfig = Field(default_factory=SeleniumConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        env_nested_delimiter = "__"
        extra = "forbid"

    @classmethod
    def _expand_env_vars(cls, content: str) -> str:
        """Expand environment variables with support for ${VAR:-default} syntax."""
        def replace_var(match):
            var_expr = match.group(1)
            if ':-' in var_expr:
                var_name, default_value = var_expr.split(':-', 1)
                return os.getenv(var_name, default_value)
            else:
                return os.getenv(var_expr, '')

        # Pattern to match ${VAR} or ${VAR:-default}
        pattern = r'\$\{([^}]+)\}'
        return re.sub(pattern, replace_var, content)

    @classmethod
    def load_from_file(cls, config_path: str) -> "ScraperConfig":
        """Load configuration from YAML or JSON file with environment variable expansion."""
        path = Path(config_path)

        if not path.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_path}")

        if path.suffix.lower() in ['.yaml', '.yml']:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
                # Expand environment variables in the YAML content
                expanded_content = cls._expand_env_vars(content)
                data = yaml.safe_load(expanded_content)
        elif path.suffix.lower() == '.json':
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
                # Expand environment variables in the JSON content
                expanded_content = cls._expand_env_vars(content)
                data = json.loads(expanded_content)
        else:
            raise ValueError(f"Unsupported config file format: {path.suffix}")

        return cls(**data)

    def get_llm_provider_config(self, task: str) -> LLMProviderConfig:
        """Get LLM configuration for a specific task."""
        task_map = {
            "parse_recommendations": self.llm.parse_recommendations,
            "choose_video": self.llm.choose_video,
            "check_relevance": self.llm.check_relevance
        }

        if task not in task_map:
            raise ValueError(f"Unknown LLM task: {task}")

        config = task_map[task]
        if config is None:
            raise ValueError(f"LLM configuration not found for task: {task}")

        return config

    def get_api_key(self, provider: str) -> Optional[str]:
        """Get API key for a specific provider."""
        key_map = {
            "openai": self.api_keys.openai,
            "azure_openai": self.api_keys.azure_openai_key,
            "openrouter": self.api_keys.openrouter
        }

        return key_map.get(provider)

    def validate_configuration(self) -> List[str]:
        """Validate configuration and return list of issues."""
        issues = []

        # Check required API keys based on configured providers
        providers_used = set()

        for config_name, config in [
            ("parse_recommendations", self.llm.parse_recommendations),
            ("choose_video", self.llm.choose_video),
            ("check_relevance", self.llm.check_relevance)
        ]:
            if config is None:
                issues.append(f"Missing LLM configuration for: {config_name}")
            else:
                providers_used.add(config.provider)

        for provider in providers_used:
            api_key = self.get_api_key(provider)
            if not api_key:
                issues.append(f"Missing API key for provider: {provider}")

            if provider == "azure_openai" and not self.api_keys.azure_openai_endpoint:
                issues.append("Missing Azure OpenAI endpoint")

        return issues

    @root_validator(skip_on_failure=True)
    def check_filter_and_mode_compatibility(cls, values):
        """
        Validates that the persona filter is not enabled for modes that do not use personas.
        """
        scraping_config = values.get('scraping')
        experiment_config = values.get('experiment')

        # Check if both configs exist before proceeding
        if scraping_config and experiment_config:
            is_filter_enabled = scraping_config.persona_filter_enabled
            is_random_mode = (experiment_config.mode == 'random_choice')

            if is_filter_enabled and is_random_mode:
                raise ValueError(
                    "Configuration Error: 'persona_filter_enabled' cannot be 'true' "
                    "when the experiment 'mode' is 'random_choice', as there is no persona to filter against."
                )

        return values


# Global configuration instance
_config: Optional[ScraperConfig] = None


def get_config() -> ScraperConfig:
    """Get the global configuration instance."""
    global _config

    if _config is None:
        # Prioritize loading from the environment variable path
        config_file_path = os.getenv('CONFIG_FILE')

        if config_file_path:
            logger.info(f"Loading configuration from specified path: {config_file_path}")
            try:
                if not Path(config_file_path).exists():
                    raise FileNotFoundError(f"Specified config file does not exist: {config_file_path}")
                _config = ScraperConfig.load_from_file(config_file_path)
            except Exception as e:
                logger.error(f"Failed to load config from {config_file_path}: {e}")
                raise  # Re-raise the exception to stop the scraper
        else:
            # Try to load from config file first
            config_paths = [
                "config.yaml",
                "config.yml",
                "config.json",
                "scraper_config.yaml",
                "scraper_config.yml",
                "scraper_config.json"
            ]

            for config_path in config_paths:
                if Path(config_path).exists():
                    try:
                        _config = ScraperConfig.load_from_file(config_path)
                        logger.info(f"Loaded configuration from: {config_path}")
                        break
                    except Exception as e:
                        logger.error(f"Failed to load config from {config_path}: {e}")
                        continue

        # Fallback to environment variables
        if _config is None:
            _config = ScraperConfig()
            logger.error("No configuration file found or specified. Scraper cannot start.")
            raise FileNotFoundError("Could not find a valid configuration file.")

        # Validate configuration
        issues = _config.validate_configuration()
        if issues:
            logger.warning("Configuration issues found:")
            for issue in issues:
                logger.warning(f"  - {issue}")

    return _config


def reload_config() -> ScraperConfig:
    """Reload configuration (useful for testing)."""
    global _config
    _config = None
    return get_config()
