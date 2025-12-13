import csv
import logging
import os
from typing import Dict, Optional

import polars as pl

from utils.errors import FileOperationError, ValidationError, error_handler, log_error
from utils.text_utils import format_text

logger = logging.getLogger(__name__)


class BSNICorrection:
    """
    Loads and applies corrections from correction_bsni.csv.
    """

    _instance = None
    _corrections: Dict[
        str, Dict[str, str]
    ] = {}  # fix_source -> {source_value -> corrected_value}
    _metadata: Dict[
        str, Dict[str, dict]
    ] = {}  # fix_source -> {source_value -> full_row_dict}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(BSNICorrection, cls).__new__(cls)
            cls._instance._load_corrections()
        return cls._instance

    @error_handler(operation_name="load_corrections", log_errors=True, re_raise=False)
    def _load_corrections(self):
        """Load corrections from CSV file."""
        csv_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "datas", "correction_bsni.csv"
        )

        if not os.path.exists(csv_path):
            log_error(
                FileOperationError(
                    f"Correction bsni file not found: {csv_path}",
                    file_path=csv_path,
                    operation="file_exists_check",
                ),
                "load_corrections",
                "warning",
            )
            return

        try:
            with open(csv_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)

                # Validate CSV headers
                expected_headers = {"fix_source", "source_value", "corrected_value"}
                if not expected_headers.issubset(set(reader.fieldnames or [])):
                    raise ValidationError(
                        f"Invalid CSV format. Expected headers: {expected_headers}, got: {reader.fieldnames}",
                        field="csv_headers",
                        value=str(reader.fieldnames),
                    )

                count = 0
                for row in reader:
                    fix_source = row.get("fix_source", "").strip()
                    source_value = row.get("source_value", "").strip()
                    corrected_value = row.get("corrected_value", "").strip()

                    if not fix_source or not source_value:
                        continue

                    # Normalize the source_value key for case-insensitive lookup
                    normalized_source_value = format_text(source_value).lower()

                    if fix_source not in self._corrections:
                        self._corrections[fix_source] = {}
                        self._metadata[fix_source] = {}

                    self._corrections[fix_source][normalized_source_value] = (
                        corrected_value
                    )
                    # Store metadata with both original and normalized keys for scope checking
                    self._metadata[fix_source][normalized_source_value] = row
                    # Also keep original for backward compatibility if needed
                    self._metadata[fix_source][source_value] = row
                    count += 1

                logger.info(f"Loaded {count} corrections from {csv_path}")
        except (IOError, OSError) as e:
            raise FileOperationError(
                f"Failed to read correction bsni file: {str(e)}",
                file_path=csv_path,
                operation="file_read",
            ) from e
        except csv.Error as e:
            raise ValidationError(
                f"Invalid CSV format in correction bsni file: {str(e)}",
                field="csv_content",
                value=csv_path,
            ) from e

    def get_correction(self, value: str, fix_source: str) -> Optional[str]:
        """
        Get corrected value for a given source value and fix source.

        This method performs case-insensitive lookup by normalizing the input value.

        Args:
            value: The value to correct
            fix_source: The source of the fix (e.g., 'bsni', 'kecamatan_index')

        Returns:
            Corrected value if found, None otherwise
        """
        if fix_source in self._corrections:
            # Normalize the lookup value for case-insensitive matching
            normalized_value = format_text(value).lower()
            return self._corrections[fix_source].get(normalized_value)
        return None

    def get_metadata(self, value: str, fix_source: str) -> Optional[dict]:
        """
        Get full metadata for a correction.

        This method performs case-insensitive lookup by normalizing the input value.

        Args:
            value: The source value
            fix_source: The source of the fix

        Returns:
            Dictionary containing the full CSV row for the correction
        """
        if fix_source in self._metadata:
            # First try normalized lookup
            normalized_value = format_text(value).lower()
            metadata = self._metadata[fix_source].get(normalized_value)
            if metadata:
                return metadata
            # Fallback to original value for backward compatibility
            return self._metadata[fix_source].get(value)
        return None

    @error_handler(operation_name="get_corrections_df", log_errors=True, re_raise=False)
    def get_corrections_df(self) -> Optional[pl.DataFrame]:
        """
        Get all corrections as a Polars DataFrame.

        Returns:
            Polars DataFrame containing all corrections, or None if import fails
        """
        csv_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "datas", "correction_bsni.csv"
        )
        try:
            if os.path.exists(csv_path):
                return pl.read_csv(csv_path)
            return None
        except (IOError, OSError) as e:
            log_error(
                FileOperationError(
                    f"Failed to read correction bsni file for DataFrame: {str(e)}",
                    file_path=csv_path,
                    operation="csv_read",
                ),
                "get_corrections_df",
                "error",
            )
            return None
        except pl.exceptions.PolarsError as e:
            log_error(
                ValidationError(
                    f"Failed to parse corrections bsni CSV: {str(e)}",
                    field="csv_parsing",
                    value=csv_path,
                ),
                "get_corrections_df",
                "error",
            )
            return None
