"""
Cache utilities for PDF structure extraction.

This module provides functions for PDF metadata extraction and cache validation
to ensure cached structure files match the current PDF file.
"""

import hashlib
import os
from typing import Optional

from models.pdf_structure import PDFCacheMetadata
from utils.errors import FileOperationError, error_handler, log_error


@error_handler(operation_name="pdf_metadata_extraction", log_errors=True)
def get_pdf_metadata(pdf_path: str) -> PDFCacheMetadata:
    """
    Extract metadata from a PDF file for caching purposes.

    Args:
        pdf_path: Path to the PDF file

    Returns:
        PDFCacheMetadata: Metadata containing file size and hash
    """
    if not os.path.exists(pdf_path):
        raise FileOperationError(
            f"PDF file not found: {pdf_path}",
            file_path=pdf_path,
            operation="file_exists_check",
        )

    # Get file size
    try:
        pdf_size = os.path.getsize(pdf_path)
    except OSError as e:
        raise FileOperationError(
            f"Failed to get PDF file size: {str(e)}",
            file_path=pdf_path,
            operation="get_file_size",
        ) from e

    # Calculate SHA256 hash of the file
    try:
        with open(pdf_path, "rb") as f:
            pdf_hash = hashlib.sha256(f.read()).hexdigest()
    except (OSError, IOError) as e:
        raise FileOperationError(
            f"Failed to read PDF file for hashing: {str(e)}",
            file_path=pdf_path,
            operation="file_read",
        ) from e

    return PDFCacheMetadata(pdf_size=pdf_size, pdf_hash=pdf_hash)


@error_handler(operation_name="cache_validation", log_errors=True, re_raise=False)
def is_cache_valid(pdf_path: str, cached_metadata: PDFCacheMetadata) -> bool:
    """
    Check if the cached structure is still valid for the current PDF file.

    Args:
        pdf_path: Path to the current PDF file
        cached_metadata: Metadata from the cached structure

    Returns:
        bool: True if cache is valid, False otherwise
    """
    try:
        current_metadata = get_pdf_metadata(pdf_path)
        return (
            current_metadata.pdf_size == cached_metadata.pdf_size
            and current_metadata.pdf_hash == cached_metadata.pdf_hash
        )
    except FileOperationError:
        # If we can't read the PDF, consider cache invalid
        return False


@error_handler(operation_name="load_cached_structure", log_errors=True, re_raise=False)
def load_cached_structure_with_validation(
    structure_path: str, pdf_path: str
) -> Optional[dict]:
    """
    Load cached structure and validate it against the current PDF file.

    Args:
        structure_path: Path to the cached structure JSON file
        pdf_path: Path to the current PDF file

    Returns:
        dict or None: Cached structure if valid, None if invalid or missing
    """
    import json

    if not os.path.exists(structure_path):
        return None

    try:
        with open(structure_path, "r", encoding="utf-8") as f:
            cached_data = json.load(f)

        # Check if cache_metadata exists in the cached data
        if "cache_metadata" not in cached_data or cached_data["cache_metadata"] is None:
            # No cache metadata available, consider cache invalid
            return None

        cached_metadata = PDFCacheMetadata(**cached_data["cache_metadata"])

        if is_cache_valid(pdf_path, cached_metadata):
            return cached_data
        else:
            return None

    except (json.JSONDecodeError, KeyError, ValueError, TypeError) as e:
        # Invalid JSON or missing required metadata - consider cache invalid
        log_error(e, "load_cached_structure", "debug")
        return None
