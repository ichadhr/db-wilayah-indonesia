#!/usr/bin/env python3
"""
Agent Analyzer: Structured Change Extraction & Validation

This script implements the Agent Analyzer for postal correction.
It processes unmapped detail records in batches, extracting structured changes from
detail_keterangan fields using LLM analysis with validation.

Usage:
    # Test with Aceh province (first batch only)
    python src/scripts/agent_analyze.py --province aceh --test

    # Process all provinces
    python src/scripts/agent_analyze.py

    # Dry run (no LLM calls)
    python src/scripts/agent_analyze.py --dry-run

    # Custom batch size
    python src/scripts/agent_analyze.py --batch-size 50
"""

# Now import everything else
import argparse
import json
import re
import sys
import time
import traceback
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Tuple

import polars as pl
from tqdm import tqdm

try:
    import jsonschema
except ImportError:
    jsonschema = None


def fuzzy_match(a, b):
    """Calculate fuzzy string similarity."""
    from difflib import SequenceMatcher

    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


# Add src directory to path FIRST before other imports
src_dir = Path(__file__).parent.parent
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from utils.llm.client import LLMClient  # noqa: E402
from utils.llm.config import LLMConfig, load_config  # noqa: E402

# ============================================================================
# CONFIGURATION CONSTANTS
# ============================================================================

DEFAULT_BATCH_SIZE = 30
UNKNOWN_PROVINCE = "unknown"

# Valid administrative field names
VALID_FIELDS = {"kecamatan", "kelurahan_desa", "kabupaten_kota"}

# Target schema columns for standardization
TARGET_COLUMNS = [
    "detail_provinsi",
    "detail_kabupaten_kota",
    "detail_kecamatan",
    "detail_kode_kelurahan",
    "detail_kelurahan_desa",
    "detail_keterangan",
    "potential_kecamatan_matches",
]


# ============================================================================
# CHANGE EXTRACTOR INTERFACE
# ============================================================================


class ChangeExtractor(ABC):
    """Abstract base class for change extraction strategies."""

    @abstractmethod
    def extract_changes(self, batch: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extract changes from a batch of records.

        Args:
            batch: Batch dictionary with data

        Returns:
            List of extraction results (one per row)
        """
        pass

    @abstractmethod
    def get_name(self) -> str:
        """Get the name of this extractor."""
        pass


# ============================================================================
# LLM CHANGE EXTRACTOR
# ============================================================================


class LLMChangeExtractor(ChangeExtractor):
    """LLM-based change extractor using structured prompts."""

    def __init__(self, config: LLMConfig):
        self.config = config
        self.llm = LLMClient(config)

    def get_name(self) -> str:
        return "LLM"

    def extract_changes(self, batch: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract changes using LLM."""
        # Format batch for LLM
        batch_markdown = self._format_batch_for_llm(batch)

        # Create prompts
        system_prompt, user_prompt = self._create_prompts(batch_markdown)

        # Call LLM with schema
        output_schema = self._build_output_schema()
        llm_response = self.llm.call_llm(
            system_prompt, user_prompt, output_schema, verbose=False
        )

        # Parse response
        result = self._parse_llm_response(llm_response)

        # Validate response structure
        self._validate_response_structure(result, batch["size"])

        return result

    def _format_batch_for_llm(self, batch: Dict[str, Any]) -> str:
        """Format batch data as markdown table for LLM input."""
        df = batch["data"]

        # Select relevant columns including current field values AND province
        columns = [
            "row_number",
            "province",
            "detail_kecamatan",
            "detail_kelurahan_desa",
            "detail_kabupaten_kota",
            "detail_keterangan",
        ]
        available_columns = [col for col in columns if col in df.columns]

        if not available_columns:
            raise ValueError("No required columns found in batch data")

        table_df = df.select(available_columns)
        table = table_df.to_pandas().to_markdown(index=False)

        return f"""## Batch Data (Rows {batch["start_row"]}-{batch["end_row"]})

{table}
"""

    def _create_prompts(self, batch_markdown: str) -> Tuple[str, str]:
        """Create system and user prompts for LLM."""

        # Load system prompt from external file
        system_prompt_path = (
            Path(__file__).parent.parent
            / "utils"
            / "llm"
            / "prompt"
            / "system_agent_analyzer.md"
        )
        with open(system_prompt_path, "r", encoding="utf-8") as f:
            system_prompt = f.read()

        # Load user prompt template from external file
        user_prompt_path = (
            Path(__file__).parent.parent
            / "utils"
            / "llm"
            / "prompt"
            / "user_agent_analyzer.md"
        )
        with open(user_prompt_path, "r", encoding="utf-8") as f:
            user_prompt_template = f.read()

        user_prompt = user_prompt_template.format(batch_markdown=batch_markdown)

        return system_prompt, user_prompt

    def _build_output_schema(self) -> Dict[str, Any]:
        """Build JSON schema for structured change extraction output."""
        return {
            "type": "array",
            "description": "Array of change extraction results, one per input row",
            "items": {
                "type": "object",
                "properties": {
                    "row_number": {
                        "type": "integer",
                        "description": "Row number from the input batch",
                    },
                    "province": {
                        "type": "string",
                        "description": "Province name for this record",
                    },
                    "changes": {
                        "type": "array",
                        "description": "Array of field-level changes extracted from detail_keterangan",
                        "items": {
                            "type": "object",
                            "properties": {
                                "field": {
                                    "type": "string",
                                    "enum": [
                                        "kecamatan",
                                        "kelurahan_desa",
                                        "kabupaten_kota",
                                    ],
                                    "description": "The field that was changed",
                                },
                                "old_name": {
                                    "type": "string",
                                    "description": "The original name before change",
                                },
                                "new_name": {
                                    "type": "string",
                                    "description": "The new name after change",
                                },
                            },
                            "required": ["field", "old_name", "new_name"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["row_number", "province", "changes"],
                "additionalProperties": False,
            },
        }

    def _build_validation_schema(self) -> Dict[str, Any]:
        """Build extended JSON schema for post-validation output structure."""
        # Start with the base extraction schema
        base_schema = self._build_output_schema()

        # Update description
        base_schema["description"] = (
            "Array of validated change extraction results with original data"
        )

        # Add original data fields to items properties
        base_schema["items"]["properties"].update(
            {
                "detail_provinsi": {
                    "type": "string",
                    "description": "Province detail from POS record",
                },
                "detail_kabupaten_kota": {
                    "type": "string",
                    "description": "Regency detail from POS record",
                },
                "detail_kecamatan": {
                    "type": "string",
                    "description": "District detail from POS record",
                },
                "detail_kode_kelurahan": {
                    "type": "string",
                    "description": "Village code from POS record",
                },
                "detail_kelurahan_desa": {
                    "type": "string",
                    "description": "Village detail from POS record",
                },
                "detail_keterangan": {
                    "type": "string",
                    "description": "Change description from POS record",
                },
                "potential_kecamatan_matches": {
                    "type": "string",
                    "description": "Potential district matches",
                },
            }
        )

        # Add validation fields to changes items properties
        base_schema["items"]["properties"]["changes"]["items"]["properties"].update(
            {
                "valid": {
                    "type": "boolean",
                    "description": "Whether this change passed validation",
                },
                "_validation_errors": {
                    "type": "array",
                    "description": "List of validation errors if any",
                    "items": {"type": "string"},
                },
            }
        )

        # Allow additional properties in changes items
        base_schema["items"]["properties"]["changes"]["items"][
            "additionalProperties"
        ] = True

        # Allow additional properties for extensibility
        base_schema["items"]["additionalProperties"] = True

        return base_schema

    def _validate_output_schema(
        self, data: List[Dict[str, Any]], schema: Dict[str, Any]
    ) -> None:
        """Validate data against the provided JSON schema."""
        if jsonschema is None:
            return  # Skip validation if jsonschema not available

        try:
            jsonschema.validate(instance=data, schema=schema)
        except jsonschema.ValidationError as e:
            raise ValueError(f"Schema validation failed: {e.message}") from e

    def _enhance_with_pos_data(
        self, extracted_data: List[Dict[str, Any]], province: str
    ) -> List[Dict[str, Any]]:
        """Enhance extracted changes using POS data cross-referencing with fuzzy matching."""
        from difflib import SequenceMatcher

        import polars as pl

        # Load POS data
        pos_file = (
            Path(__file__).parent.parent
            / "log"
            / province
            / f"{province}_remain_unmapped_pos.csv"
        )
        if not pos_file.exists():
            print(f"  Warning: POS file not found: {pos_file}")
            return extracted_data

        pos_df = pl.read_csv(pos_file)

        # Normalize hierarchy for matching
        pos_df = pos_df.with_columns(
            pl.col("kabupaten_kota")
            .str.to_lowercase()
            .str.strip_chars()
            .alias("kab_lower"),
            pl.col("kecamatan").str.to_lowercase().str.strip_chars().alias("kec_lower"),
        )

        # Convert to list for easier iteration
        all_pos_records = pos_df.rows(named=True)

        # Enhance each extracted record
        enhanced_data = []
        for record in extracted_data:
            enhanced_record = record.copy()
            changes = record.get("changes", [])

            # Always check for missing hierarchy corrections (kecamatan/kabupaten)
            existing_fields = {change.get("field") for change in changes}
            kab = record.get("detail_kabupaten_kota", "").lower().strip()
            kel_detail = record.get("detail_kelurahan_desa", "")

            # Get all POS records in the same kabupaten for cross-kecamatan fuzzy matching
            pos_records = [
                record for record in all_pos_records if record["kab_lower"] == kab
            ]

            # Find best matching POS record for village correction
            best_match = None
            best_score = 0

            for pos_record in pos_records:
                # Simple fuzzy match on kecamatan (since kab should match)
                kec_score = SequenceMatcher(
                    None,
                    pos_record["kecamatan"],
                    record.get("detail_kecamatan", ""),
                ).ratio()
                score = kec_score  # Could add village similarity too

                if score > best_score and score > 0.8:  # High similarity threshold
                    best_match = pos_record
                    best_score = score

            # Fallback: If no good match in exact kabupaten, try fuzzy kabupaten search
            if best_match is None:
                for pos_record in all_pos_records:
                    # Fuzzy match on both kabupaten and kecamatan
                    kab_score = fuzzy_match(
                        pos_record["kabupaten_kota"],
                        record.get("detail_kabupaten_kota", ""),
                    )
                    kec_score = fuzzy_match(
                        pos_record["kecamatan"], record.get("detail_kecamatan", "")
                    )

                    # Weight: 40% kabupaten, 60% kecamatan (kabupaten changes are rarer)
                    score = (kab_score * 0.4) + (kec_score * 0.6)

                    if (
                        score > best_score and score > 0.85
                    ):  # Higher threshold for cross-kabupaten
                        best_match = pos_record
                        best_score = score

            # Generate corrections for hierarchy and village mismatches
            inferred_changes = []
            if best_match:
                pos_kec = best_match["kecamatan"]
                detail_kec = record.get("detail_kecamatan", "")

                # Kecamatan correction (if names differ significantly and not already present)
                if (
                    pos_kec != detail_kec
                    and "kecamatan" not in existing_fields
                    and SequenceMatcher(None, pos_kec, detail_kec).ratio() < 1.0
                ):
                    inferred_changes.append(
                        {
                            "field": "kecamatan",
                            "old_name": pos_kec,
                            "new_name": detail_kec,
                            "valid": True,
                            "reason": "Inferred from POS hierarchy fuzzy match",
                        }
                    )

                # Kabupaten correction (rare but possible)
                pos_kab = best_match["kabupaten_kota"]
                kab_similarity = fuzzy_match(
                    pos_kab, record.get("detail_kabupaten_kota", "")
                )
                if (
                    pos_kab != record.get("detail_kabupaten_kota", "")
                    and "kabupaten_kota" not in existing_fields
                    and kab_similarity < 1.0
                ):
                    inferred_changes.append(
                        {
                            "field": "kabupaten_kota",
                            "old_name": pos_kab,
                            "new_name": record["detail_kabupaten_kota"],
                            "valid": True,
                            "reason": f"Inferred from fuzzy hierarchy match (score: {kab_similarity:.2f})",
                        }
                    )

                # Village correction (if not already present)
                pos_kel = best_match.get("desa_kelurahan", "")
                if (
                    pos_kel
                    and kel_detail
                    and pos_kel != kel_detail
                    and "kelurahan_desa" not in existing_fields
                ):
                    inferred_changes.append(
                        {
                            "field": "kelurahan_desa",
                            "old_name": pos_kel,
                            "new_name": kel_detail,
                            "valid": True,
                            "reason": "Inferred from POS hierarchy fuzzy match",
                        }
                    )

            # Add inferred changes to existing changes (avoiding duplicates)
            if inferred_changes:
                enhanced_record["changes"] = changes + inferred_changes
                print(
                    f"  Enhanced record {record['row_number']}: added {len(inferred_changes)} inferred changes"
                )
            else:
                enhanced_record["changes"] = changes

            enhanced_data.append(enhanced_record)

        return enhanced_data

    def _parse_llm_response(self, llm_response: Any) -> List[Dict[str, Any]]:
        """Parse LLM response into structured format."""
        if isinstance(llm_response, str):
            try:
                result = json.loads(llm_response)
            except json.JSONDecodeError as e:
                # Save raw response for debugging
                debug_file = (
                    Path(__file__).parent.parent
                    / "debug"
                    / f"llm_raw_response_error_{int(time.time())}.json"
                )
                debug_file.parent.mkdir(exist_ok=True)
                with open(debug_file, "w", encoding="utf-8") as f:
                    f.write(llm_response)
                raise ValueError(f"Invalid JSON response (saved to {debug_file}): {e}")
        else:
            result = llm_response

        return result

    def _validate_response_structure(self, result: Any, expected_size: int) -> None:
        """Validate basic structure of LLM response."""
        if not isinstance(result, list):
            raise ValueError("LLM response is not a list")

        if len(result) != expected_size:
            raise ValueError(
                f"Response length {len(result)} doesn't match batch size {expected_size}"
            )


# ============================================================================
# POST-PROCESSING FUNCTIONS
# ============================================================================


def normalize_old_names(
    data: List[Dict[str, Any]], verbose: bool = False
) -> List[Dict[str, Any]]:
    """
    Add missing administrative prefixes to old_name by checking detail_keterangan context.

    Args:
        data: List of extraction results
        verbose: If True, print normalization details

    Returns:
        Normalized data with corrected old_name values
    """

    def generate_prefix_variations(base_prefixes: List[str]) -> List[str]:
        """Generate all common variations of administrative prefixes."""
        variations = set()
        for base in base_prefixes:
            variations.add(base)
            variations.add(base + ".")
            variations.add(base + " ")
            variations.add(base + ". ")
            if "." in base:
                no_dot = base.replace(".", "")
                variations.add(no_dot)
                variations.add(no_dot + " ")
        return list(variations)

    def has_prefix(text: str, prefixes: List[str]) -> bool:
        """Check if text already starts with any administrative prefix."""
        text_lower = text.lower().strip()
        return any(text_lower.startswith(prefix.lower()) for prefix in prefixes)

    def find_prefix_before_name(keterangan: str, name: str, prefixes: List[str]) -> str:
        """Find the prefix immediately before the name in keterangan."""
        name_pattern = re.compile(re.escape(name), re.IGNORECASE)
        matches = list(name_pattern.finditer(keterangan))

        if not matches:
            return ""

        match = matches[0]
        start_pos = match.start()
        text_before = keterangan[:start_pos].strip()
        words_before = text_before.split()

        if not words_before:
            return ""

        # Check last 1-2 words for prefix match
        for i in range(len(words_before) - 1, max(-1, len(words_before) - 3), -1):
            candidate = " ".join(words_before[i:])
            for prefix in prefixes:
                if candidate.lower().endswith(prefix.lower()):
                    # Return the actual prefix as it appears in the text (preserve case)
                    return candidate[-len(prefix) :].strip()

        return ""

    # Generate prefix variations
    base_prefixes = ["ds", "kp"]
    prefixes = generate_prefix_variations(base_prefixes)

    normalized_data = []

    for item in data:
        changes = item.get("changes", [])
        keterangan = item.get("detail_keterangan", "")

        normalized_changes = []
        for change in changes:
            old_name = change.get("old_name", "").strip()

            # Skip if old_name is empty
            if not old_name:
                normalized_changes.append(change)
                continue

            # Skip if already has prefix
            if has_prefix(old_name, prefixes):
                normalized_changes.append(change)
                continue

            # Find prefix in keterangan
            found_prefix = find_prefix_before_name(keterangan, old_name, prefixes)

            if found_prefix:
                normalized_old = f"{found_prefix} {old_name}"
                normalized_change = change.copy()
                normalized_change["old_name"] = normalized_old

                if verbose:
                    print(f"Normalized: '{old_name}' → '{normalized_old}'")

                normalized_changes.append(normalized_change)
            else:
                normalized_changes.append(change)

        normalized_item = item.copy()
        normalized_item["changes"] = normalized_changes
        normalized_data.append(normalized_item)

    return normalized_data


def validate_changes(
    output: List[Dict[str, Any]], batch_data: pl.DataFrame
) -> List[Dict[str, Any]]:
    """
    Validate extracted changes and mark each as valid/invalid.
    Include original record data for context.

    Args:
        output: LLM output array
        batch_data: Original batch DataFrame for context

    Returns:
        Validated output with original data and validated changes
    """
    # Create lookup using composite key (province, row_number) to handle duplicates across provinces
    original_data_lookup = {}
    for row in batch_data.iter_rows(named=True):
        composite_key = (row["province"], row["row_number"])
        original_data_lookup[composite_key] = row

    validated_output = []

    for item in output:
        row_number = item.get("row_number")
        province = item.get("province")

        # Skip if row_number or province is invalid
        if row_number is None or not isinstance(row_number, int):
            print(f"Warning: Skipping item with invalid row_number: {row_number}")
            continue

        if province is None or not isinstance(province, str):
            print(f"Warning: Skipping item with invalid province: {province}")
            continue

        changes = item.get("changes", [])

        # Use composite key for lookup
        composite_key = (province, row_number)
        original_record = original_data_lookup.get(composite_key, {})

        if not original_record:
            print(f"Warning: No original record found for {province} row {row_number}")
            continue

        validated_changes = []

        for change in changes:
            validated_change = _validate_single_change(change, original_record)
            validated_changes.append(validated_change)

        # Build complete validated item with original data
        validated_item = _build_validated_item(
            row_number, original_record, validated_changes
        )
        validated_output.append(validated_item)

    return validated_output


def _validate_single_change(
    change: Dict[str, Any], original_record: Dict[str, Any]
) -> Dict[str, Any]:
    """Validate a single change against the original record."""
    field = change.get("field")
    old_name = str(change.get("old_name", "")).strip()
    new_name = str(change.get("new_name", "")).strip()

    is_valid = True
    errors = []

    # 1. Field validity
    if field not in VALID_FIELDS:
        is_valid = False
        errors.append(f"Invalid field: {field}")

    # 2. old_name ≠ new_name
    if old_name == new_name:
        is_valid = False
        errors.append("old_name equals new_name")

    # 3. Verify new_name matches current record value
    field_key = f"detail_{field}"
    current_value = str(original_record.get(field_key, "")).strip()

    if new_name != current_value:
        is_valid = False
        errors.append(
            f"new_name '{new_name}' does not match current value '{current_value}'"
        )

    # 4. Non-empty values
    if not old_name or not new_name:
        is_valid = False
        errors.append("Empty old_name or new_name")

    # Build validated change
    validated_change = {
        "field": field,
        "old_name": old_name,
        "new_name": new_name,
        "valid": is_valid,
    }

    if not is_valid and errors:
        validated_change["_validation_errors"] = errors

    return validated_change


def _build_validated_item(
    row_number: int, original_record: Dict[str, Any], validated_changes: List[Dict]
) -> Dict[str, Any]:
    """Build complete validated item with original data."""
    validated_item = {
        "row_number": row_number,
        "province": str(original_record.get("province", "")),
        "detail_provinsi": str(original_record.get("detail_provinsi", "")),
        "detail_kabupaten_kota": str(original_record.get("detail_kabupaten_kota", "")),
        "detail_kecamatan": str(original_record.get("detail_kecamatan", "")),
        "detail_kode_kelurahan": str(original_record.get("detail_kode_kelurahan", "")),
        "detail_kelurahan_desa": str(original_record.get("detail_kelurahan_desa", "")),
        "detail_keterangan": str(original_record.get("detail_keterangan", "")),
        "potential_kecamatan_matches": str(
            original_record.get("potential_kecamatan_matches", "")
        ),
        "changes": validated_changes,
    }

    # Remove empty fields to keep JSON clean
    validated_item = {k: v for k, v in validated_item.items() if v != ""}

    return validated_item


# ============================================================================
# AGENT ANALYZER MAIN CLASS
# ============================================================================


class AgentAnalyzer:
    """
    Agent Analyzer: Extracts structured changes from detail_keterangan
    using pluggable extractors with validation.
    """

    def __init__(self, config: LLMConfig, extractor: ChangeExtractor):
        """Initialize Agent Analyzer with configuration and extractor."""
        self.config = config
        self.extractor = extractor

    def load_unmapped_data(
        self, province_filter: str | None = None
    ) -> Tuple[pl.DataFrame, int, int]:
        """
        Load and merge unmapped detail records from provinces.

        Args:
            province_filter: If set, load only this province

        Returns:
            Tuple of (Combined DataFrame, total_original_rows, total_skipped_rows)
        """
        if province_filter:
            print(f"Loading unmapped detail records for province: {province_filter}")
        else:
            print("Loading unmapped detail records from all provinces...")

        all_data = []
        provinces_found = 0
        total_original_rows = 0
        total_skipped_rows = 0

        # Iterate through province directories
        for province_dir in self.config.output_log_dir.iterdir():
            if not province_dir.is_dir():
                continue

            province = province_dir.name

            # Skip if filtering and doesn't match
            if province_filter and province != province_filter:
                continue

            detail_file = province_dir / f"{province}_remain_unmapped_detail.csv"

            if not detail_file.exists():
                continue

            # Load and process province data
            df, original_count, skipped_count = self._load_province_data(
                detail_file, province
            )

            if df is not None:
                all_data.append(df)
                provinces_found += 1
                total_original_rows += original_count
                total_skipped_rows += skipped_count
                print(f"  - {province}: {len(df)} records with content")

        if not all_data:
            raise ValueError("No unmapped detail records found")

        # Combine all provinces
        combined_df = pl.concat(all_data, how="vertical_relaxed")
        print(f"\nTotal: {len(combined_df)} records from {provinces_found} provinces")
        print(f"Total original rows: {total_original_rows}")
        print(f"Total skipped rows (empty detail_keterangan): {total_skipped_rows}")

        return combined_df, total_original_rows, total_skipped_rows

    def _load_province_data(
        self, detail_file: Path, province: str
    ) -> Tuple[pl.DataFrame | None, int, int]:
        """Load and preprocess data for a single province."""
        try:
            df = pl.read_csv(detail_file)

            if len(df) == 0:
                return None, 0, 0

            original_count = len(df)

            # Standardize schema
            df = self._standardize_schema(df)

            # Add province and row tracking (original row numbers per province)
            df = df.with_columns(
                [
                    pl.lit(province).alias("province"),
                    pl.arange(1, len(df) + 1).alias("row_number"),
                ]
            )

            # Preprocess: strip leading sequence numbers from kelurahan_desa
            if "detail_kelurahan_desa" in df.columns:
                df = df.with_columns(
                    pl.col("detail_kelurahan_desa").str.replace(
                        r"^\d+\s*", "", literal=False
                    )
                )

            # Filter out rows with empty detail_keterangan
            if "detail_keterangan" in df.columns:
                df = df.filter(
                    pl.col("detail_keterangan").is_not_null()
                    & (pl.col("detail_keterangan") != "")
                )

            filtered_count = len(df)
            skipped_count = original_count - filtered_count

            if filtered_count == 0:
                return None, original_count, skipped_count

            return df, original_count, skipped_count

        except Exception as e:
            print(f"  - {province}: ERROR - {e}")
            return None, 0, 0

    def _standardize_schema(self, df: pl.DataFrame) -> pl.DataFrame:
        """Standardize DataFrame schema by adding missing columns."""
        # Add missing columns with null values
        for col in TARGET_COLUMNS:
            if col not in df.columns:
                df = df.with_columns(pl.lit(None).cast(pl.Utf8).alias(col))

        # Select only target columns
        df = df.select(TARGET_COLUMNS)

        return df

    def create_batches(self, df: pl.DataFrame, batch_size: int) -> List[Dict[str, Any]]:
        """
        Split data into batches for processing.

        Args:
            df: Combined DataFrame
            batch_size: Number of rows per batch

        Returns:
            List of batch dictionaries
        """
        batches = []
        total_rows = len(df)

        for start_idx in range(0, total_rows, batch_size):
            end_idx = min(start_idx + batch_size, total_rows)
            batch_df = df.slice(start_idx, end_idx - start_idx)

            batch = {
                "batch_id": f"batch_{len(batches) + 1}",
                "start_row": start_idx + 1,
                "end_row": end_idx,
                "data": batch_df,
                "size": len(batch_df),
            }
            batches.append(batch)

        print(f"Created {len(batches)} batches (batch_size={batch_size})")
        return batches

    def process_batch(
        self, batch: Dict[str, Any], dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Process a single batch through extractor.

        Args:
            batch: Batch dictionary
            dry_run: If True, skip extraction

        Returns:
            Processing result
        """
        batch_id = batch["batch_id"]

        if dry_run:
            return {
                "batch_id": batch_id,
                "status": "dry_run",
                "size": batch["size"],
                "extractor": self.extractor.get_name(),
            }

        try:
            # Extract changes
            result = self.extractor.extract_changes(batch)

            # Validate changes
            validated_result = validate_changes(result, batch["data"])

            # Normalize old_name format
            validated_result = normalize_old_names(validated_result, verbose=False)

            # Enhance with POS data cross-referencing (optional)
            # Only for LLM extractor to fill gaps in extracted changes
            if isinstance(self.extractor, LLMChangeExtractor):
                # Check if batch contains records from single province only
                unique_provinces = batch["data"].select("province").unique()
                if len(unique_provinces) == 1:
                    province = unique_provinces.item()
                    validated_result = self.extractor._enhance_with_pos_data(
                        validated_result, province
                    )
                # Skip enhancement for mixed-province batches

            # Validate final output structure (only for LLM extractor)
            if isinstance(self.extractor, LLMChangeExtractor):
                validation_schema = self.extractor._build_validation_schema()
                self.extractor._validate_output_schema(
                    validated_result, validation_schema
                )

            return {
                "batch_id": batch_id,
                "status": "success",
                "data": validated_result,
                "size": batch["size"],
            }

        except Exception as e:
            return {
                "batch_id": batch_id,
                "status": "error",
                "error": str(e),
            }

    def save_results(
        self, results: List[Dict[str, Any]], province_filter: str | None = None
    ) -> None:
        """
        Save results to province-specific JSON files.

        Args:
            results: List of batch results
            province_filter: If set, save directly to that province
        """
        # Collect all successful results
        all_results = []
        for result in results:
            if result["status"] == "success":
                all_results.extend(result["data"])

        if not all_results:
            print("  No successful results to save")
            return

        if province_filter:
            # Single province mode
            self._save_province_results(province_filter, all_results)
        else:
            # Multi-province mode - split by province
            self._save_multi_province_results(all_results)

    def _save_multi_province_results(self, all_results: List[Dict[str, Any]]) -> None:
        """Split and save results by province."""
        print("  Splitting results by province...")

        # Group results by province
        province_groups = {}
        for item in all_results:
            province = item.get("province", UNKNOWN_PROVINCE)
            if province not in province_groups:
                province_groups[province] = []
            province_groups[province].append(item)

        # Save each province group
        for province, province_results in province_groups.items():
            if province == UNKNOWN_PROVINCE:
                print(
                    f"  Warning: {len(province_results)} results with unknown province"
                )
                continue

            self._save_province_results(province, province_results)

    def _save_province_results(self, province: str, data: List[Dict[str, Any]]) -> None:
        """Save results for a specific province."""
        # Convert province name to folder format
        province_folder = province.lower().replace(" ", "_")

        # Get project root (src/scripts/agent_analyze.py -> project root)
        src_dir = Path(__file__).parent.parent
        output_dir = src_dir / "datas" / "comparing_pos" / province_folder / "raw"
        output_dir.mkdir(parents=True, exist_ok=True)

        output_file = output_dir / f"{province_folder}_analyze.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print(f"  Saved {len(data)} results to {output_file}")

    def run_analysis(
        self,
        dry_run: bool = False,
        batch_size: int = DEFAULT_BATCH_SIZE,
        province_filter: str | None = None,
        test_mode: bool = False,
    ) -> Dict[str, Any]:
        """
        Run complete analysis pipeline.

        Args:
            dry_run: If True, skip LLM calls
            batch_size: Number of rows per batch
            province_filter: Process only this province
            test_mode: If True, process only first batch

        Returns:
            Analysis summary
        """
        print(f"\n{'=' * 80}")
        if province_filter:
            print(
                f"Agent Analyzer: Processing {province_filter.replace('_', ' ').title()} Province"
            )
        else:
            print("Agent Analyzer: Structured Change Extraction & Validation")
        print(f"{'=' * 80}\n")

        try:
            # Load data
            all_data, total_original_rows, total_skipped_rows = self.load_unmapped_data(
                province_filter
            )

            # Create batches
            batches = self.create_batches(all_data, batch_size)

            # Test mode: process only first batch
            if test_mode:
                batches = batches[:1]
                print("TEST MODE: Processing only first batch\n")

            # Process batches
            results = []
            failed_batches = []

            for batch in tqdm(batches, desc="Processing batches"):
                result = self.process_batch(batch, dry_run)

                if result["status"] == "success":
                    results.append(result)
                else:
                    failed_batches.append(result)

            # Report failures
            if failed_batches:
                print(f"\n{len(failed_batches)} batches failed:")
                for failed in failed_batches:
                    print(f"  - {failed['batch_id']}: {failed.get('error', 'unknown')}")

            # Save results
            if results and not dry_run:
                print(f"\nSaving {len(results)} successful batch results...")
                self.save_results(results, province_filter)

            # Summary
            self._print_summary(
                results,
                batches,
                failed_batches,
                total_original_rows,
                total_skipped_rows,
                province_filter,
            )

            return {
                "status": "completed",
                "successful_batches": len(results),
                "total_batches": len(batches),
                "total_rows": sum(r["size"] for r in results),
                "total_original_rows": total_original_rows,
                "total_skipped_rows": total_skipped_rows,
                "failed_batches": len(failed_batches),
            }

        except Exception as e:
            print(f"\n{'=' * 80}")
            print("AGENT ANALYZER FAILED")
            print(f"{'=' * 80}")
            print(traceback.format_exc())
            return {"status": "error", "error": str(e)}

    def _print_summary(
        self,
        results: List[Dict],
        batches: List[Dict],
        failed_batches: List[Dict],
        total_original_rows: int,
        total_skipped_rows: int,
        province_filter: str | None = None,
    ) -> None:
        """Print analysis summary."""
        print(f"\n{'=' * 80}")
        if province_filter:
            print(
                f"AGENT ANALYZER COMPLETE - {province_filter.replace('_', ' ').title()}"
            )
        else:
            print("AGENT ANALYZER COMPLETE")
        print(f"{'=' * 80}")
        print(f"Successful batches: {len(results)}/{len(batches)}")
        print(f"Total rows processed: {sum(r['size'] for r in results)}")
        print(f"Total original rows: {total_original_rows}")
        print(f"Total rows skipped (empty detail_keterangan): {total_skipped_rows}")
        print(f"Failed batches: {len(failed_batches)}")
        print(f"{'=' * 80}\n")


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Agent Analyzer: Structured Change Extraction",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Test with Aceh province (first batch only)
  python src/scripts/agent_analyze.py --province aceh --test

  # Process all provinces
  python src/scripts/agent_analyze.py

  # Dry run (no LLM calls)
  python src/scripts/agent_analyze.py --dry-run

  # Custom batch size
  python src/scripts/agent_analyze.py --batch-size 50
        """,
    )
    parser.add_argument(
        "--province",
        type=str,
        help="Process only this specific province (e.g., aceh, jawa_barat)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=f"Number of rows per batch (default: {DEFAULT_BATCH_SIZE})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Test run without calling LLM (skips extraction)",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Test mode: process only the first batch",
    )

    args = parser.parse_args()

    try:
        # Load configuration
        print("Loading LLM configuration...")
        config = load_config(dry_run=args.dry_run)
        print(f"[OK] Provider: {config.llm_provider}")
        print(f"[OK] Model: {config.llm_model}")

        # Create extractor
        extractor = LLMChangeExtractor(config)
        print(f"[OK] Using {extractor.get_name()} extractor\n")

        # Initialize analyzer
        analyzer = AgentAnalyzer(config, extractor)

        # Run analysis
        result = analyzer.run_analysis(
            dry_run=args.dry_run,
            batch_size=args.batch_size,
            province_filter=args.province,
            test_mode=args.test,
        )

        if result["status"] == "completed":
            print("[OK] Agent Analyzer completed successfully!")
            sys.stdout.flush()
            sys.exit(0)
        else:
            print(f"[FAIL] Agent Analyzer failed: {result.get('error')}")
            sys.exit(1)

    except Exception as e:
        print(f"\nFatal error: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
