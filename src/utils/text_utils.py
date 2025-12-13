import functools
import re
from typing import TYPE_CHECKING, Any, Literal, Optional

if TYPE_CHECKING:
    from models.kode_wilayah import KodeWilayah


def format_number(s):
    return str(s).replace(".", "")


def format_luas(s):
    return str(s).replace(".", "").replace(",", ".")


def format_pulau(s):
    return str(s).replace(",", "")


def format_string(s):
    """Format string for CSV output by escaping special characters and handling Unicode."""
    if s is None:
        return ""

    # Convert to string and handle Unicode properly
    original_s = str(s)

    # Check if original string contains special characters that require quoting
    needs_quoting = (
        "," in original_s
        or '"' in original_s
        or "\n" in original_s
        or "\r" in original_s
    )

    # Replace newlines and tabs with spaces for the final output
    s = original_s.replace("\n", " ").replace("\r", " ").replace("\t", " ")

    # Remove extra whitespace while preserving single spaces
    s = " ".join(s.split())

    # If string needs quoting (based on original content), wrap in quotes and escape quotes
    if needs_quoting:
        s = s.replace('"', '""')  # Escape quotes by doubling them
        s = f'"{s}"'  # Wrap in quotes

    return s


def format_text(text: str) -> str:
    """
    Normalize text by cleaning whitespace and newlines.

    This is a general-purpose text cleaning function that:
    - Replaces newlines and tabs with spaces
    - Normalizes multiple whitespace to single spaces
    - Strips leading/trailing whitespace

    Used for general text processing (not CSV-specific).
    """
    if text is None:
        return ""

    # Convert to string
    text = str(text)

    # Replace newlines, carriage returns, and tabs with spaces
    text = text.replace("\n", " ").replace("\r", " ").replace("\t", " ")

    # Normalize whitespace (multiple spaces become single space)
    text = " ".join(text.split())

    return text.strip()


def clean_leading_number(text: str) -> str:
    """
    Remove leading numbers from text (e.g., "1. Name" → "Name").

    Args:
        text: Input text that may contain leading numbers

    Returns:
        Text with leading numbers removed
    """
    if not text:
        return ""
    return re.sub(r"^\d+\.?\s+", "", text)


@functools.lru_cache(maxsize=None)
def _get_abbreviation_pattern(province: str) -> Optional[re.Pattern]:
    """
    Get cached compiled regex pattern for province-specific abbreviations.

    Args:
        province: Province name (case-insensitive)

    Returns:
        Compiled regex pattern or None if no abbreviations for the province
    """
    province_abbreviations = {
        "aceh": ["meunasah", "matang glumpang dua", "meuna", "kp"],
        "nusa_tenggara_barat": ["kampung", "dusun"],
    }

    abbreviations = province_abbreviations.get(province.lower(), [])
    if not abbreviations:
        return None
    pattern = r"\b(" + "|".join(abbreviations) + r")\.?\s+"
    return re.compile(pattern, re.IGNORECASE)


def normalize_for_matching(
    text: str,
    field_type: Literal[
        "province", "kabupaten", "kelurahan", "kecamatan"
    ] = "kelurahan",
    province: Optional[str] = None,
) -> str:
    """
    Normalize Indonesian place names for fuzzy matching.

    Handles:
    - Common abbreviations based on province context
    - Whitespace normalization
    - Numbered prefixes for kelurahan names

    Args:
        text: Input text to normalize
        field_type: Type of field ('kelurahan' or 'kecamatan')
        province: Province name for context-aware abbreviation removal (optional)

    Returns:
        Normalized text ready for fuzzy matching
    """
    if not text:
        return ""

    # Start with base normalization (handles whitespace)
    text = format_text(text)
    text = text.lower()

    # Normalize common prefix variations for kelurahan
    if field_type == "kelurahan":
        # Remove numbered prefixes (e.g., "1. Name" -> "Name")
        text = re.sub(r"^\d+\s*[-.]?\s*", "", text)

        # Commented out abbreviation removal to log all pure unmatched records
        # without abbreviation normalization for documentation in comparing_pos/{province}.md
        # if province:
        #     pattern = _get_abbreviation_pattern(province)
        #     if pattern:
        #         text = pattern.sub('', text)

    # Remove all spaces after all processing
    text = text.replace(" ", "")

    return text


def convert_cyrillic_to_latin(text: str) -> str:
    """
    Convert Cyrillic characters that look like Latin digits to their Latin equivalents.
    Used for OCR text correction where Cyrillic characters may be misrecognized.

    Args:
        text: Input text that may contain Cyrillic characters

    Returns:
        Text with Cyrillic characters converted to Latin equivalents
    """
    # Mapping of Cyrillic characters to Latin equivalents
    cyrillic_to_latin_map = {
        # Digits that look similar
        "З": "3",
        "Б": "8",
        # Uppercase letters
        "А": "A",
        "В": "B",
        "Е": "E",
        "К": "K",
        "М": "M",
        "Н": "H",
        "О": "O",
        "Р": "P",
        "С": "C",
        "Т": "T",
        "Х": "X",
        "У": "Y",
        "Ү": "Y",  # Kazakh/Mongolian Ү
        "І": "I",
        "Ї": "I",
        "Ё": "E",
        # Lowercase letters
        "а": "a",
        "в": "b",
        "е": "e",
        "к": "k",
        "м": "m",
        "н": "h",
        "о": "o",
        "р": "p",
        "с": "c",
        "т": "t",
        "у": "y",
        "х": "x",
        "і": "i",
        "ї": "i",
        "ё": "e",
        # Additional mappings from original function
        "з": "3",
        "б": "6",
        "Ч": "4",
        "ч": "4",
        "ү": "y",
    }

    result = text
    for cyrillic, latin in cyrillic_to_latin_map.items():
        result = result.replace(cyrillic, latin)

    return result


def kode_wilayah(raw_record: dict) -> Optional["KodeWilayah"]:
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
    from models.kode_wilayah import KodeWilayah

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
        "singkatan_nama_kota": _clean_field(
            processed.get("singkatan_nama_kota", ""), uppercase=True
        ),
        "parent_subdivision": _clean_field(
            processed.get("parent_subdivision", ""), uppercase=True
        ),
    }

    return KodeWilayah(**cleaned)


def normalize_kabupaten_kota(text: str) -> str:
    """
    Normalize kabupaten/kota names by expanding abbreviations.

    Args:
        text: Input kabupaten/kota name

    Returns:
        Normalized kabupaten/kota name
    """
    if not text:
        return ""

    # Convert to title case for consistency
    text = text.strip()

    # Expand common abbreviations
    replacements = {
        r"\bKab\.\s*": "Kabupaten ",
        r"\bKab\b": "Kabupaten",
        r"\bKota\b": "Kota",
        r"\bKep\.\s*": "Kepulauan ",
    }

    for pattern, replacement in replacements.items():
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

    # Clean up extra spaces
    text = " ".join(text.split())

    return text


def normalize_ibukota_kabupaten_kota(text: str) -> str:
    """
    Normalize ibukota/kabupaten/kota names by expanding abbreviations and removing suffixes.

    Args:
        text: Input text that may contain abbreviations or suffixes

    Returns:
        Text with abbreviations expanded to full forms and suffixes removed
    """

    if not text:
        return ""

    # First clean the text
    text = format_text(text)

    # Expand common abbreviations and remove suffixes (case-insensitive)
    replacements = [
        (r", Kec\..*$", "", re.IGNORECASE),
        (r"\bP\.\s+", "Pulau ", re.IGNORECASE),
        # Add other abbreviations as needed
    ]

    for pattern, replacement, flags in replacements:
        text = re.sub(pattern, replacement, text, flags=flags)

    return text


def normalize_kecamatan(text: str) -> str:
    """
    Normalize kecamatan names by removing leading numbers and expanding abbreviations.

    Args:
        text: Input kecamatan name

    Returns:
        Normalized kecamatan name
    """
    if not text:
        return ""

    # Handle newlines, tabs, and carriage returns
    text = text.replace("\n", " ").replace("\r", " ").replace("\t", " ")

    text = text.strip()

    # Remove leading numbers (e.g., "1. Name" → "Name")
    text = clean_leading_number(text)

    # Expand abbreviations
    replacements = {
        r"(?i)\bKec\.\s*": "Kecamatan ",
        r"(?i)\bKec\b": "Kecamatan",
    }

    for pattern, replacement in replacements.items():
        text = re.sub(pattern, replacement, text)

    # Clean up extra spaces
    text = " ".join(text.split())

    return text


def normalize_kelurahan_desa(text: str) -> str:
    """
    Normalize kelurahan/desa names by removing leading numbers and expanding abbreviations.

    Args:
        text: Input kelurahan/desa name

    Returns:
        Normalized kelurahan/desa name
    """
    if not text:
        return ""

    # Handle newlines, tabs, and carriage returns
    text = text.replace("\n", " ").replace("\r", " ").replace("\t", " ")

    text = text.strip()

    # Remove leading numbers (e.g., "1. Name" → "Name")
    text = clean_leading_number(text)

    # Expand abbreviations
    replacements = {
        r"(?i)\bKel\.\s*": "Kelurahan ",
        r"(?i)\bKel\b": "Kelurahan",
        r"(?i)\bDs\.\s*": "Desa ",
        r"(?i)\bDs\b": "Desa",
        r"(?i)\bDesa\b": "Desa",
        r"(?i)\bKelurahan\b": "Kelurahan",
        r"(?i)\bKamp\.\s*": "Kampung ",
        r"(?i)\bKamp\b": "Kampung",
        r"(?i)\bDus\.\s*": "Dusun ",
        r"(?i)\bDus\b": "Dusun",
        r"(?i)\bMns\.\s*": "Meunasah ",
        r"(?i)\bKampong\b": "Kampung",
        r"(?i)\bGampong\b": "Kampung",
    }

    for pattern, replacement in replacements.items():
        text = re.sub(pattern, replacement, text)

    # Clean up extra spaces
    text = " ".join(text.split())

    return text


def _clean_field(value: Any, uppercase: bool = False) -> str:
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
