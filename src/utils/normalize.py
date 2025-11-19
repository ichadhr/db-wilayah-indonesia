"""
Data normalization utilities for kode wilayah processing.

This module provides functions to normalize and clean data from OCR processing,
including Cyrillic character conversion and field cleaning.
"""

import re
from typing import Optional

from models.kode_wilayah import KodeWilayah
from utils.converter import convert_cyrillic_to_latin


def kode_wilayah(raw_record: dict) -> Optional[KodeWilayah]:
    """
    Normalize and create KodeWilayah instance from raw OCR record.
    
    This function processes raw OCR data by:
    - Converting Cyrillic characters to Latin equivalents
    - Extracting and validating the 'no' field
    - Cleaning string fields (removing HTML tags, trimming whitespace)
    - Creating a validated KodeWilayah instance

    Args:
        raw_record: Raw dictionary from OCR processing containing fields like
                   'no', 'provinsi', 'kabupaten_kota', 'nama_kota', etc.

    Returns:
        KodeWilayah instance if valid, None if the record is invalid
        (e.g., missing or invalid 'no' field)
        
    Example:
        >>> raw = {
        ...     'no': '1',
        ...     'provinsi': 'ACEH',
        ...     'nama_kota': 'Banda Aceh'
        ... }
        >>> kw = kode_wilayah(raw)
        >>> kw.no
        1
    """
    # Convert Cyrillic characters
    processed = {}
    for key, value in raw_record.items():
        if isinstance(value, str) and re.search(r"[\u0400-\u04FF]", value):
            processed[key] = convert_cyrillic_to_latin(value)
        else:
            processed[key] = value

    # Extract and validate 'no' field
    no_str = re.sub(r"\D", "", str(processed.get("no", "")))
    if not no_str:
        return None
    no = int(no_str)

    # Clean string fields
    cleaned = {
        "no": no,
        "provinsi": _clean_field(processed.get("provinsi", "")),
        "kabupaten_kota": _clean_field(processed.get("kabupaten_kota", "")),
        "nama_kota": _clean_field(processed.get("nama_kota", "")),
        "singkatan_nama_kota": _clean_field(processed.get("singkatan_nama_kota", ""), uppercase=True),
        "parent_subdivision": _clean_field(processed.get("parent_subdivision", ""), uppercase=True),
    }

    return KodeWilayah(**cleaned)


def _clean_field(value: any, uppercase: bool = False) -> str:
    """
    Clean a field value by removing HTML tags and trimming whitespace.
    
    Args:
        value: The value to clean (will be converted to string)
        uppercase: If True, convert the result to uppercase
        
    Returns:
        Cleaned string value
    """
    cleaned = str(value).strip().replace("<br>", " ")
    return cleaned.upper() if uppercase else cleaned
