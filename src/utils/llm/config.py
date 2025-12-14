"""
LLM Configuration Management for Postal Code Correction System.

This module provides configuration management for LLM providers using Pydantic settings.
Supports multiple providers via LiteLLM (OpenAI, Anthropic, Google, Ollama, etc.).
"""

from pathlib import Path
from typing import Literal, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMConfig(BaseSettings):
    """Configuration for LLM-based postal code correction system."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore"
    )

    # LLM Provider Settings
    llm_provider: Literal[
        "openai",
        "anthropic",
        "google",
        "gemini",
        "azure",
        "ollama",
        "bedrock",
        "mistral",
    ] = Field(default="openai", description="LLM provider to use")

    llm_model: str = Field(
        default="gpt-4-turbo-preview", description="Model name specific to the provider"
    )

    llm_temperature: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Sampling temperature (0=deterministic, 1=creative)",
    )

    llm_max_tokens: Optional[int] = Field(
        default=16384,
        ge=256,
        le=200000,
        description="Maximum tokens for LLM response (None = use model default)",
    )

    llm_timeout: int = Field(
        default=300, ge=10, le=3600, description="Timeout for LLM calls in seconds"
    )

    llm_base_url: Optional[str] = Field(
        default=None, description="Base URL for local models or custom endpoints"
    )

    # API Keys (provider-specific)
    openai_api_key: Optional[str] = Field(default=None, description="OpenAI API key")
    anthropic_api_key: Optional[str] = Field(
        default=None, description="Anthropic API key"
    )
    google_api_key: Optional[str] = Field(default=None, description="Google API key")
    azure_api_key: Optional[str] = Field(default=None, description="Azure API key")
    azure_api_base: Optional[str] = Field(
        default=None, description="Azure API base URL"
    )
    azure_api_version: Optional[str] = Field(
        default=None, description="Azure API version"
    )
    mistral_api_key: Optional[str] = Field(default=None, description="Mistral API key")

    # Confidence Thresholds
    confidence_threshold_auto_apply: float = Field(
        default=0.80,
        ge=0.0,
        le=1.0,
        description="Minimum confidence for auto-applying corrections",
    )

    confidence_threshold_flag: float = Field(
        default=0.70,
        ge=0.0,
        le=1.0,
        description="Minimum confidence before flagging as low",
    )

    # Output Configuration
    output_markdown_dir: Path = Field(
        default=Path("src/datas/comparing_pos"),
        description="Directory for markdown output",
    )

    output_json_dir: Path = Field(
        default=Path("src/datas/comparing_pos"), description="Directory for JSON output"
    )

    output_log_dir: Path = Field(
        default=Path("src/log"), description="Directory for diagnostic logs"
    )

    @field_validator(
        "output_markdown_dir", "output_json_dir", "output_log_dir", mode="before"
    )
    @classmethod
    def resolve_paths(cls, v: str | Path) -> Path:
        """Resolve paths to absolute paths."""
        path = Path(v)
        if not path.is_absolute():
            # Resolve relative to project root (4 levels up from src/utils/llm/)
            project_root = Path(__file__).parent.parent.parent.parent
            path = project_root / path
        return path

    @field_validator("confidence_threshold_flag")
    @classmethod
    def validate_threshold_order(cls, v: float, info) -> float:
        """Ensure flag threshold is less than auto-apply threshold."""
        auto_apply = info.data.get("confidence_threshold_auto_apply", 0.80)
        if v > auto_apply:
            raise ValueError(
                f"confidence_threshold_flag ({v}) must be <= "
                f"confidence_threshold_auto_apply ({auto_apply})"
            )
        return v

    def get_api_key(self) -> Optional[str]:
        """Get API key for the configured provider."""
        key_mapping = {
            "openai": self.openai_api_key,
            "anthropic": self.anthropic_api_key,
            "google": self.google_api_key,
            "gemini": self.google_api_key,
            "azure": self.azure_api_key,
            "mistral": self.mistral_api_key,
        }
        return key_mapping.get(self.llm_provider)

    def validate_provider_config(self, dry_run: bool = False) -> None:
        """Validate that required configuration exists for the selected provider."""
        # Skip validation in dry-run mode
        if dry_run:
            return

        # Local models (Ollama) don't need API keys
        if self.llm_provider == "ollama":
            if not self.llm_base_url:
                raise ValueError(
                    "llm_base_url is required for Ollama provider "
                    "(e.g., http://localhost:11434)"
                )
            return

        # Cloud providers need API keys
        api_key = self.get_api_key()
        if not api_key:
            raise ValueError(
                f"API key not configured for provider '{self.llm_provider}'. "
                f"Please set the appropriate environment variable."
            )

        # Azure needs additional configuration
        if self.llm_provider == "azure":
            if not self.azure_api_base or not self.azure_api_version:
                raise ValueError(
                    "Azure provider requires azure_api_base and azure_api_version"
                )

    def get_litellm_params(self) -> dict:
        """Get parameters for LiteLLM API call."""
        # Use model name only for OpenAI with custom base URL, otherwise use provider/model format
        if self.llm_base_url and self.llm_provider == "openai":
            model_param = self.llm_model
        else:
            model_param = f"{self.llm_provider}/{self.llm_model}"
        params = {
            "model": model_param,
            "temperature": self.llm_temperature,
        }

        # Only set max_tokens if it's not None (allows model to use default)
        if self.llm_max_tokens is not None:
            params["max_tokens"] = self.llm_max_tokens

        # Set timeout
        params["timeout"] = self.llm_timeout

        # Add API key if available
        api_key = self.get_api_key()
        if api_key:
            params["api_key"] = api_key

        # Add base URL for local/custom endpoints
        if self.llm_base_url:
            params["api_base"] = self.llm_base_url
            # Force OpenAI provider when using custom base URL to avoid model name-based routing
            if self.llm_provider == "openai":
                params["custom_llm_provider"] = "openai"

        # Add Azure-specific parameters
        if self.llm_provider == "azure":
            params["api_version"] = self.azure_api_version
            params["api_base"] = self.azure_api_base

        return params


def load_config(dry_run: bool = False) -> LLMConfig:
    """Load and validate LLM configuration."""
    config = LLMConfig()
    config.validate_provider_config(dry_run=dry_run)
    return config
