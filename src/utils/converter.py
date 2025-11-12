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


def convert_cyrillic_to_latin(text: str) -> str:
    """
    Convert Cyrillic characters that look like Latin digits to their Latin equivalents.
    Used for OCR text correction where Cyrillic characters may be misrecognized.

    Args:
        text: Input text that may contain Cyrillic characters

    Returns:
        Text with Cyrillic look-alike characters converted to Latin
    """
    if not text:
        return text

    # Mapping of Cyrillic characters that look like Latin digits
    cyr_to_lat = {
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
    }

    result = text
    for cyr, lat in cyr_to_lat.items():
        result = result.replace(cyr, lat)

    return result


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
    text = text.replace('\n', ' ').replace('\r', ' ').replace('\t', ' ')

    # Normalize whitespace (multiple spaces become single space)
    text = ' '.join(text.split())

    return text.strip()


def normalize_kabupaten_kota(text: str) -> str:
    """
    Normalize kabupaten/kota names by expanding abbreviations.

    Args:
        text: Input text that may contain abbreviations

    Returns:
        Text with abbreviations expanded to full forms
    """
    import re

    if not text:
        return ""

    # First clean the text
    text = format_text(text)

    # Expand common abbreviations (case-insensitive)
    replacements = [
        (r'^\d+\.?\s+', '', 0),
        (r'^kab\s+', 'Kabupaten ', re.IGNORECASE),
        (r'\badm\.\s+', 'Administrasi ', re.IGNORECASE),
        # Add other abbreviations as needed
    ]

    for pattern, replacement, flags in replacements:
        text = re.sub(pattern, replacement, text, flags=flags)

    return text


def normalize_ibukota_kabupaten_kota(text: str) -> str:
    """
    Normalize ibukota/kabupaten/kota names by expanding abbreviations and removing suffixes.

    Args:
        text: Input text that may contain abbreviations or suffixes

    Returns:
        Text with abbreviations expanded to full forms and suffixes removed
    """
    import re

    if not text:
        return ""

    # First clean the text
    text = format_text(text)

    # Expand common abbreviations and remove suffixes (case-insensitive)
    replacements = [
        (r', Kec\..*$', '', re.IGNORECASE),
        (r'\bP\.\s+', 'Pulau ', re.IGNORECASE)
        # Add other abbreviations as needed
    ]

    for pattern, replacement, flags in replacements:
        text = re.sub(pattern, replacement, text, flags=flags)

    return text


def normalize_kecamatan(text: str) -> str:
    """
    Normalize kecamatan names by expanding abbreviations.

    Args:
        text: Input text that may contain abbreviations

    Returns:
        Text with abbreviations expanded to full forms
    """
    import re

    if not text:
        return ""

    # First clean the text
    text = format_text(text)

    # Expand common abbreviations (case-insensitive)
    replacements = [
        (r'^\d+', '', 0),  # Remove leading digits
        (r'\bKec\.\s*', 'Kecamatan ', re.IGNORECASE),
        # Add other abbreviations as needed
    ]

    for pattern, replacement, flags in replacements:
        text = re.sub(pattern, replacement, text, flags=flags)

    return text


def normalize_kelurahan_desa(text: str) -> str:
    """
    Normalize kelurahan/desa names by expanding abbreviations.

    Args:
        text: Input text that may contain abbreviations

    Returns:
        Text with abbreviations expanded to full forms
    """
    import re

    if not text:
        return ""

    # First clean the text
    text = format_text(text)

    # Expand common abbreviations (case-insensitive)
    replacements = [
        (r'^\d+\.?\s+', '', 0),  # Existing: Remove leading numbers
        (r'\bKel\.\s*', 'Kelurahan ', re.IGNORECASE),
        (r'\bDs\.\s*', 'Desa ', re.IGNORECASE),
        (r'\bKamp\.\s*', 'Kampung ', re.IGNORECASE),
        (r'\bDus\.\s*', 'Dusun ', re.IGNORECASE),
    ]

    for pattern, replacement, flags in replacements:
        text = re.sub(pattern, replacement, text, flags=flags)

    return text
