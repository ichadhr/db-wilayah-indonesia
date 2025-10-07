"""
Data normalization utilities for kode wilayah processing.
"""

import re

from models.kode_wilayah import KodeWilayah
from utils.converter import convert_cyrillic_to_latin


def kode_wilayah(raw_record: dict) -> KodeWilayah | None:
    """
    Normalize and create KodeWilayah instance from raw OCR record.

    Args:
        raw_record: Raw dictionary from OCR processing

    Returns:
        KodeWilayah instance or None if invalid
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
        "provinsi": str(processed.get("provinsi", "")).strip().replace("<br>", " "),
        "kabupaten_kota": str(processed.get("kabupaten_kota", ""))
        .strip()
        .replace("<br>", " "),
        "nama_kota": str(processed.get("nama_kota", "")).strip().replace("<br>", " "),
        "singkatan_nama_kota": str(processed.get("singkatan_nama_kota", ""))
        .strip()
        .replace("<br>", " ")
        .upper(),
        "parent_subdivision": str(processed.get("parent_subdivision", ""))
        .strip()
        .replace("<br>", " ")
        .upper(),
    }

    return KodeWilayah(**cleaned)
