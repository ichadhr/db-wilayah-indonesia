"""
Structure Utilities

This module provides utilities for working with PDF structure data,
including functions to extract section information by type with Polars DataFrames.
"""

import json
from typing import List, Optional

import polars as pl
from models.pdf_structure import AdministrativeStructure


def load_structure(json_path: str) -> AdministrativeStructure:
    """Load AdministrativeStructure from JSON file."""
    with open(json_path, 'r', encoding='utf-8') as f:
        structure_data = json.load(f)
    return AdministrativeStructure(**structure_data)


def provinsi(json_path: str) -> pl.DataFrame:
    """Get province index section as Polars DataFrame."""
    structure = load_structure(json_path)

    data = [{
        "name": structure.name,
        "table_format": structure.table_format,
        "start_page": structure.page_range.start,
        "end_page": structure.page_range.end
    }]

    return pl.DataFrame(data)


def kabupaten_kota_index(json_path: str, province_names: Optional[List[str]] = None) -> pl.DataFrame:
    """Get kabupaten/kota index sections as Polars DataFrame, optionally filtered by province names."""
    structure = load_structure(json_path)
    sections_data = []

    for province in structure.provinces:
        if province_names is None or province.name in province_names:
            section = province.sections.kabupaten_kota_index
            sections_data.append({
                "province_name": province.name,
                "type": section.type,
                "name": section.name,
                "table_format": section.table_format,
                "start_page": section.page_range.start,
                "end_page": section.page_range.end
            })

    return pl.DataFrame(sections_data)


def kecamatan_index(json_path: str, province_names: Optional[List[str]] = None) -> pl.DataFrame:
    """Get kecamatan index sections as Polars DataFrame, optionally filtered by province names."""
    structure = load_structure(json_path)
    sections_data = []

    for province in structure.provinces:
        if province_names is None or province.name in province_names:
            section = province.sections.kecamatan_index
            sections_data.append({
                "province_name": province.name,
                "type": section.type,
                "name": section.name,
                "table_format": section.table_format,
                "start_page": section.page_range.start,
                "end_page": section.page_range.end
            })

    return pl.DataFrame(sections_data)


def kabupaten_kota_detail(json_path: str, province_names: Optional[List[str]] = None) -> pl.DataFrame:
    """Get kabupaten/kota detail sections as Polars DataFrame, optionally filtered by province names."""
    structure = load_structure(json_path)
    details_data = []

    for province in structure.provinces:
        if province_names is None or province.name in province_names:
            for detail in province.details:
                details_data.append({
                    "province_name": province.name,
                    "id": detail.id,
                    "name": detail.name,
                    "table_format": detail.table_format,
                    "region_type": detail.region_type,
                    "start_page": detail.page_range.start,
                    "end_page": detail.page_range.end
                })

    return pl.DataFrame(details_data)