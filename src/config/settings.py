"""Application settings using pydantic-settings."""

from pathlib import Path
from typing import List, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def get_project_root() -> Path:
    """Get the project root directory (src/) relative to this settings file."""
    # This file is in src/config/, so go up two levels to get src/
    return Path(__file__).parent.parent


def validate_log_level_value(v: str) -> str:
    """Shared validator for log level fields."""
    allowed_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
    if v.upper() not in allowed_levels:
        raise ValueError(f"log_level must be one of {allowed_levels}")
    return v.upper()


class PipelineSettings(BaseSettings):
    """Settings for the data pipeline."""

    # Pipeline settings
    batch_size: int = Field(default=38, description="Number of provinces per batch")
    max_workers: int = Field(default=7, description="Concurrent threads")
    debug_mode: bool = Field(default=False, description="Enable debug mode")
    force_restructure: bool = Field(
        default=False, description="Force PDF structure re-extraction"
    )

    # Processing options
    province_filter: Optional[List[str]] = Field(
        default=None,
        description="Specific provinces to process (empty list means all provinces)",
    )

    # File paths
    main_pdf: str = Field(default="", description="Full path to the main PDF file")

    data_directory: str = Field(
        default="datas", description="Directory containing input data files"
    )
    output_directory: str = Field(
        default="output", description="Base output directory for generated files"
    )
    debug_directory: str = Field(
        default="debug", description="Directory for debug output files"
    )

    # Logging configuration
    log_level: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
    )
    log_directory: str = Field(default="log", description="Directory for log files")

    model_config = SettingsConfigDict(
        env_file_encoding="utf-8", env_prefix="PIPELINE_", extra="ignore"
    )

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level is one of the allowed values."""
        allowed_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in allowed_levels:
            raise ValueError(f"log_level must be one of {allowed_levels}")
        return v.upper()

    @field_validator("batch_size", "max_workers")
    @classmethod
    def validate_positive_int(cls, v: int) -> int:
        """Validate that integer values are positive."""
        if v <= 0:
            raise ValueError("Value must be positive")
        return v

    @field_validator("main_pdf")
    @classmethod
    def validate_main_pdf(cls, v: str) -> str:
        """Validate main PDF file exists if specified."""
        if v:
            # Resolve relative paths against project root
            if not Path(v).is_absolute():
                resolved_path = get_project_root() / v
            else:
                resolved_path = Path(v)

            if not resolved_path.exists():
                raise ValueError(f"Main PDF file does not exist: {resolved_path}")
            return str(resolved_path)
        return v

    @field_validator(
        "data_directory", "output_directory", "debug_directory", "log_directory"
    )
    @classmethod
    def resolve_directory_path(cls, v: str) -> str:
        """Resolve directory paths relative to project root."""
        if not Path(v).is_absolute():
            return str(get_project_root() / v)
        return v

    def get_main_pdf_path(self) -> Optional[Path]:
        """Get the full path to the main PDF file."""
        if not self.main_pdf:
            return None
        return Path(self.main_pdf)

    def get_output_path(self, *subdirs: str) -> Path:
        """Get output path with optional subdirectories."""
        return Path(self.output_directory, *subdirs)

    def get_debug_path(self, *subdirs: str) -> Path:
        """Get debug path with optional subdirectories."""
        return Path(self.debug_directory, *subdirs)

    def get_log_path(self) -> Path:
        """Get log directory path."""
        return Path(self.log_directory)


class LoggingSettings(BaseSettings):
    """Settings specifically for logging configuration."""

    level: str = Field(default="INFO", description="Logging level")
    directory: str = Field(default="log", description="Log directory")
    format: str = Field(
        default="%(asctime)s - %(levelname)s - %(message)s",
        description="Log message format",
    )

    model_config = SettingsConfigDict(
        env_file=str(get_project_root() / ".env"),
        env_file_encoding="utf-8",
        env_prefix="LOG_",
        extra="ignore",
    )

    @field_validator("level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level is one of the allowed values."""
        allowed_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in allowed_levels:
            raise ValueError(f"log_level must be one of {allowed_levels}")
        return v.upper()


class Settings(BaseSettings):
    """Main application settings."""

    pipeline: PipelineSettings = Field(default_factory=PipelineSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)

    model_config = SettingsConfigDict(env_file_encoding="utf-8", extra="ignore")


# Global settings instance
settings = Settings()
