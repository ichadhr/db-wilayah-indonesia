"""
Pydantic models for postal code correction and matching operations.
"""

from typing import Optional
from pydantic import BaseModel, Field, field_validator


class NormalizedDetailRecord(BaseModel):
    """Normalized detail record from government documents."""

    kode_kelurahan: str = Field(..., description="Unique kelurahan code")
    kelurahan: str = Field("", description="Kelurahan name")
    desa: str = Field("", description="Desa name")
    kecamatan: str = Field(..., description="Kecamatan name")
    kabupaten_kota: str = Field(..., description="Kabupaten/Kota name")
    provinsi: str = Field(..., description="Province name")
    original_provinsi: str = Field(..., description="Original province name from source")
    keterangan: str = Field("", description="Additional notes")

    # Normalized fields for matching
    kelurahan_normalized: str = Field("", description="Normalized kelurahan name")
    desa_normalized: str = Field("", description="Normalized desa name")
    kecamatan_normalized: str = Field("", description="Normalized kecamatan name")
    kelurahan_desa_combined: str = Field("", description="Combined kelurahan and desa for matching")

    @field_validator("kode_kelurahan", "kelurahan", "desa", "kecamatan",
                     "kabupaten_kota", "provinsi", "original_provinsi", "keterangan",
                     "kelurahan_normalized", "desa_normalized", "kecamatan_normalized",
                     "kelurahan_desa_combined", mode="before")
    @classmethod
    def validate_str_fields(cls, v):
        return str(v) if v is not None else ""


class NormalizedPosRecord(BaseModel):
    """Normalized POS record from postal service data."""

    kabupaten_kota_source: str = Field(..., description="Source kabupaten/kota name")
    kecamatan: str = Field(..., description="Kecamatan name")
    desa_kelurahan: str = Field(..., description="Desa/Kelurahan name")
    provinsi: str = Field(..., description="Province name")
    original_provinsi: str = Field(..., description="Original province name from source")
    kodepos: str = Field(..., description="Postal code")

    # Normalized fields for matching
    kecamatan_normalized: str = Field("", description="Normalized kecamatan name")
    desa_kelurahan_normalized: str = Field("", description="Normalized desa/kelurahan name")

    @field_validator("kabupaten_kota_source", "kecamatan", "desa_kelurahan",
                     "provinsi", "original_provinsi", "kodepos",
                     "kecamatan_normalized", "desa_kelurahan_normalized", mode="before")
    @classmethod
    def validate_str_fields(cls, v):
        return str(v) if v is not None else ""


class MatchedRecord(BaseModel):
    """Record representing a successful match between detail and POS data."""

    kode_kelurahan: str = Field(..., description="Unique kelurahan code")
    kabupaten_kota: str = Field(..., description="Kabupaten/Kota name")
    kecamatan: str = Field(..., description="Kecamatan name")
    kelurahan: str = Field("", description="Kelurahan name")
    desa: str = Field("", description="Desa name")
    keterangan: str = Field("", description="Additional notes")
    original_provinsi: str = Field(..., description="Original province name")
    provinsi: str = Field(..., description="Normalized province name")
    kodepos: str = Field(..., description="Matched postal code")

    # Confidence scores
    overall_confidence: float = Field(..., description="Overall match confidence score")

    # Similarity scores (for fuzzy matches)
    provinsi_similarity: Optional[float] = Field(None, description="Province similarity score")
    kabupaten_similarity: Optional[float] = Field(None, description="Kabupaten similarity score")
    kecamatan_similarity: Optional[float] = Field(None, description="Kecamatan similarity score")
    kelurahan_similarity: Optional[float] = Field(None, description="Kelurahan similarity score")

    # POS source data
    pos_original_provinsi: Optional[str] = Field(None, description="POS original province")
    pos_kelurahan_desa: Optional[str] = Field(None, description="POS kelurahan/desa name")

    @field_validator("kode_kelurahan", "kabupaten_kota", "kecamatan", "kelurahan",
                     "desa", "keterangan", "original_provinsi", "provinsi", "kodepos",
                     "pos_original_provinsi", "pos_kelurahan_desa", mode="before")
    @classmethod
    def validate_str_fields(cls, v):
        return str(v) if v is not None else ""

    @field_validator("overall_confidence", "provinsi_similarity", "kabupaten_similarity",
                     "kecamatan_similarity", "kelurahan_similarity", mode="before")
    @classmethod
    def validate_float_fields(cls, v):
        if v is None:
            return None
        return float(v) if v != "" else None


class UnmatchedDetailRecord(BaseModel):
    """Detail record that could not be matched with POS data."""

    kode_kelurahan: str = Field(..., description="Unique kelurahan code")
    kelurahan: str = Field("", description="Kelurahan name")
    desa: str = Field("", description="Desa name")
    kecamatan: str = Field(..., description="Kecamatan name")
    kabupaten_kota: str = Field(..., description="Kabupaten/Kota name")
    provinsi: str = Field(..., description="Province name")
    original_provinsi: str = Field(..., description="Original province name from source")
    keterangan: str = Field("", description="Additional notes")

    # Normalized fields
    kelurahan_normalized: str = Field("", description="Normalized kelurahan name")
    desa_normalized: str = Field("", description="Normalized desa name")
    kecamatan_normalized: str = Field("", description="Normalized kecamatan name")
    kelurahan_desa_combined: str = Field("", description="Combined kelurahan and desa for matching")

    # LLM hints for potential matches
    potential_kecamatan_matches: Optional[str] = Field(None, description="Potential kecamatan matches from similarity analysis")

    @field_validator("kode_kelurahan", "kelurahan", "desa", "kecamatan",
                     "kabupaten_kota", "provinsi", "original_provinsi", "keterangan",
                     "kelurahan_normalized", "desa_normalized", "kecamatan_normalized",
                     "kelurahan_desa_combined", "potential_kecamatan_matches", mode="before")
    @classmethod
    def validate_str_fields(cls, v):
        return str(v) if v is not None else ""


class UnmappedPosRecord(BaseModel):
    """POS record that could not be matched with detail data."""

    kabupaten_kota_source: str = Field(..., description="Source kabupaten/kota name")
    kecamatan: str = Field(..., description="Kecamatan name")
    desa_kelurahan: str = Field(..., description="Desa/Kelurahan name")
    provinsi: str = Field(..., description="Province name")
    original_provinsi: str = Field(..., description="Original province name from source")
    kodepos: str = Field(..., description="Postal code")

    # Normalized fields
    kecamatan_normalized: str = Field("", description="Normalized kecamatan name")
    desa_kelurahan_normalized: str = Field("", description="Normalized desa/kelurahan name")

    @field_validator("kabupaten_kota_source", "kecamatan", "desa_kelurahan",
                     "provinsi", "original_provinsi", "kodepos",
                     "kecamatan_normalized", "desa_kelurahan_normalized", mode="before")
    @classmethod
    def validate_str_fields(cls, v):
        return str(v) if v is not None else ""


class MatchResult(BaseModel):
    """Container for the results of a postal code matching operation."""

    exact_matches: list[MatchedRecord] = Field(default_factory=list, description="Records matched exactly")
    fuzzy_matches: list[MatchedRecord] = Field(default_factory=list, description="Records matched using fuzzy logic")
    unmatched_detail: list[UnmatchedDetailRecord] = Field(default_factory=list, description="Detail records without matches")
    unmapped_pos: list[UnmappedPosRecord] = Field(default_factory=list, description="POS records without matches")

    # Statistics
    total_detail_records: int = Field(0, description="Total detail records processed")
    total_pos_records: int = Field(0, description="Total POS records processed")
    exact_match_count: int = Field(0, description="Number of exact matches")
    fuzzy_match_count: int = Field(0, description="Number of fuzzy matches")
    unmatched_detail_count: int = Field(0, description="Number of unmatched detail records")
    unmapped_pos_count: int = Field(0, description="Number of unmapped POS records")
    overall_match_rate: float = Field(0.0, description="Overall match rate percentage")

    @field_validator("overall_match_rate", mode="before")
    @classmethod
    def validate_match_rate(cls, v):
        return float(v) if v is not None else 0.0