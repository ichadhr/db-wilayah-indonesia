"""
Structure Utilities

This module provides utilities for working with PDF structure data,
including functions to extract section information by type with Polars DataFrames.
"""

import json
from typing import List, Optional

import polars as pl

from models.pdf_structure import AdministrativeStructure
from utils.errors import FileOperationError, ValidationError, error_handler


@error_handler(operation_name="load_structure", log_errors=True)
def load_structure(json_path: str) -> AdministrativeStructure:
    """Load AdministrativeStructure from JSON file."""
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            structure_data = json.load(f)
    except (IOError, OSError) as e:
        raise FileOperationError(
            f"Failed to read structure JSON file: {str(e)}",
            file_path=json_path,
            operation="file_read",
        ) from e
    except json.JSONDecodeError as e:
        raise ValidationError(
            f"Invalid JSON format in structure file: {str(e)}",
            field="json_content",
            value=json_path,
        ) from e

    try:
        return AdministrativeStructure(**structure_data)
    except (TypeError, ValueError) as e:
        raise ValidationError(
            f"Invalid structure data format: {str(e)}",
            field="structure_data",
            value=json_path,
        ) from e


def validate_dataframe_schema(df: pl.DataFrame, expected_columns: List[str]) -> bool:
    """Validate DataFrame has expected columns."""
    return set(df.columns) == set(expected_columns)


def _get_province_section_struct(
    json_path: str, section_attr: str, province_names: Optional[List[str]] = None
) -> pl.DataFrame:
    """Helper function to get province section data as Polars DataFrame."""
    structure = load_structure(json_path)
    sections_data = []

    for province in structure.provinces:
        if province_names is None or province.name in province_names:
            try:
                section = getattr(province.sections, section_attr)
            except AttributeError:
                raise ValueError(f"Unknown section attribute: {section_attr}")
            sections_data.append(
                {
                    "province_name": province.name,
                    "type": section.type,
                    "name": section.name,
                    "table_format": section.table_format,
                    "start_page": section.page_range.start,
                    "end_page": section.page_range.end,
                }
            )

    df = pl.DataFrame(sections_data)
    expected_columns = [
        "province_name",
        "type",
        "name",
        "table_format",
        "start_page",
        "end_page",
    ]
    if not validate_dataframe_schema(df, expected_columns):
        raise ValidationError(
            f"Schema validation failed for {section_attr}. Expected: {expected_columns}, Got: {df.columns}",
            field="dataframe_schema",
            value=str(df.columns),
        )
    return df


def provinsi_index_struct(json_path: str) -> pl.DataFrame:
    """Get province index section as Polars DataFrame."""
    structure = load_structure(json_path)

    data = [
        {
            "name": structure.name,
            "table_format": structure.table_format,
            "start_page": structure.page_range.start,
            "end_page": structure.page_range.end,
        }
    ]

    df = pl.DataFrame(data)
    expected_columns = ["name", "table_format", "start_page", "end_page"]
    if not validate_dataframe_schema(df, expected_columns):
        raise ValidationError(
            f"Schema validation failed for provinsi_index_struct. Expected: {expected_columns}, Got: {df.columns}",
            field="dataframe_schema",
            value=str(df.columns),
        )
    return df


def kabupaten_kota_index_struct(
    json_path: str, province_names: Optional[List[str]] = None
) -> pl.DataFrame:
    """Get kabupaten/kota index sections as Polars DataFrame, optionally filtered by province names."""
    return _get_province_section_struct(
        json_path, "kabupaten_kota_index", province_names
    )


def kecamatan_index_struct(
    json_path: str, province_names: Optional[List[str]] = None
) -> pl.DataFrame:
    """Get kecamatan index sections as Polars DataFrame, optionally filtered by province names."""
    return _get_province_section_struct(json_path, "kecamatan_index", province_names)


def kabupaten_kota_detail_struct(
    json_path: str, province_names: Optional[List[str]] = None
) -> pl.DataFrame:
    """Get kabupaten/kota detail sections as Polars DataFrame, optionally filtered by province names."""
    structure = load_structure(json_path)
    details_data = []

    for province in structure.provinces:
        if province_names is None or province.name in province_names:
            for detail in province.details:
                details_data.append(
                    {
                        "province_name": province.name,
                        "id": detail.id,
                        "name": detail.name,
                        "table_format": detail.table_format,
                        "region_type": detail.region_type,
                        "start_page": detail.page_range.start,
                        "end_page": detail.page_range.end,
                    }
                )

    df = pl.DataFrame(details_data)
    expected_columns = [
        "province_name",
        "id",
        "name",
        "table_format",
        "region_type",
        "start_page",
        "end_page",
    ]
    if not validate_dataframe_schema(df, expected_columns):
        raise ValidationError(
            f"Schema validation failed for kabupaten_kota_detail_struct. Expected: {expected_columns}, Got: {df.columns}",
            field="dataframe_schema",
            value=str(df.columns),
        )
    return df
