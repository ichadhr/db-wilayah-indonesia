"""Data models for PDF extraction and regional data."""

from .kode_wilayah import KodeWilayah
from .pdf_structure import AdministrativeStructure
from .pdf_table import (
    ProvinceIndexData,
    RegencyIndexData,
    DistrictIndexData,
    DetailsData
)
from .pos_correction import (
    NormalizedDetailRecord,
    NormalizedPosRecord,
    MatchedRecord,
    UnmatchedDetailRecord,
    UnmappedPosRecord,
    MatchResult
)
from .output import PostalMatcherOutput

__all__ = [
    'KodeWilayah',
    'AdministrativeStructure',
    'ProvinceIndexData',
    'RegencyIndexData',
    'DistrictIndexData',
    'DetailsData',
    'NormalizedDetailRecord',
    'NormalizedPosRecord',
    'MatchedRecord',
    'UnmatchedDetailRecord',
    'UnmappedPosRecord',
    'MatchResult',
    'PostalMatcherOutput',
]