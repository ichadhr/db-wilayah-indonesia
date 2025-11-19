"""Data models for PDF extraction and regional data."""

from .kode_wilayah import KodeWilayah
from .pdf_structure import AdministrativeStructure
from .pdf_table import (
    ProvinceIndexData,
    RegencyIndexData,
    DistrictIndexData,
    DetailsData
)

__all__ = [
    'KodeWilayah',
    'AdministrativeStructure',
    'ProvinceIndexData',
    'RegencyIndexData',
    'DistrictIndexData',
    'DetailsData',
]