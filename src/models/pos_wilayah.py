from typing import List

from pydantic import BaseModel, field_validator

from utils.text_utils import format_text, normalize_kabupaten_kota


class PosWilayah(BaseModel):
    kodepos: str
    desa_kelurahan: str
    kecamatan: str
    kabupaten_kota: str
    provinsi: str
    kabupaten_kota_source: str  # Original name from index file for joining

    @field_validator(
        "kodepos",
        "desa_kelurahan",
        "kecamatan",
        "kabupaten_kota",
        "provinsi",
        "kabupaten_kota_source",
        mode="before",
    )
    @classmethod
    def validate_str_fields(cls, v):
        """Normalize string fields to clean newlines and extra whitespace."""
        return format_text(v)

    @field_validator("kabupaten_kota", mode="before")
    @classmethod
    def validate_kabupaten_kota_field(cls, v):
        """Normalize kabupaten_kota field by expanding abbreviations."""
        return normalize_kabupaten_kota(v)


class TablePosWilayah(BaseModel):
    records: List[PosWilayah]
