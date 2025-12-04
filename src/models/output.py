"""
Output configuration models for postal code matching operations.
"""

from pathlib import Path
from pydantic import BaseModel, Field, field_validator


class PostalMatcherOutput(BaseModel):
    """Output configuration for postal code matching operations."""

    # Directory paths
    parquet_dir: Path = Field(..., description="Base directory containing province parquet files")
    log_dir: Path = Field(..., description="Output directory for logs and results")

    # File suffixes
    detail_suffix: str = Field("_kabupaten_kota_detail.parquet", description="Suffix for detail parquet files")
    pos_suffix: str = Field("_kabupaten_kota_pos.parquet", description="Suffix for POS parquet files")

    @field_validator("parquet_dir", "log_dir", mode="before")
    @classmethod
    def validate_path_fields(cls, v):
        if isinstance(v, str):
            return Path(v)
        return v

    @field_validator("detail_suffix", "pos_suffix", mode="before")
    @classmethod
    def validate_str_fields(cls, v):
        return str(v)