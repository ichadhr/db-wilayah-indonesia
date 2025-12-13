"""
Prompt Engineering Utilities for LLM-based Postal Code Correction.

This module builds simplified prompts for LLM analysis of unmapped postal code records,
incorporating core instructions and validation rules.
"""

import json
from pathlib import Path
from typing import Any

import polars as pl


def build_system_prompt() -> str:
    """Build simplified system prompt with core instructions and validation rules."""
    prompt_path = Path(__file__).parent / "prompt" / "system_prompt.md"
    with open(prompt_path, 'r', encoding='utf-8') as f:
        return f.read()


def build_examples_context() -> str:
    """Build diverse regional examples for context."""
    prompt_path = Path(__file__).parent / "prompt" / "example_context.md"
    with open(prompt_path, 'r', encoding='utf-8') as f:
        return f.read()

def build_output_schema() -> dict[str, Any]:
    """Build JSON schema for the final simplified format."""
    return {
        "type": "object",
        "properties": {
            "corrections": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "original_pos_data": {
                            "type": "object",
                            "description": "Complete original POS record data - ALL required fields",
                            "properties": {
                                "province": {"type": "string"},
                                "regency_city": {"type": "string"},
                                "kecamatan": {"type": "string"},
                                "desa_kelurahan": {"type": "string"}
                            },
                            "required": ["province", "regency_city", "kecamatan", "desa_kelurahan"],
                            "additionalProperties": False
                        },
                        "corrections": {
                            "type": "array",
                            "minItems": 1,
                            "description": "Array of corrections - only fields that actually changed",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "field": {
                                        "type": "string",
                                        "enum": ["kecamatan", "desa_kelurahan", "kabupaten_kota"]
                                    },
                                    "corrected_value": {"type": "string"},
                                    "reasoning": {"type": "string", "maxLength": 150},
                                    "confidence": {"type": "number", "minimum": 0.70, "maximum": 1.0}
                                },
                                "required": ["field", "corrected_value", "reasoning", "confidence"]
                            }
                        },
                        "references": {"type": "string"},
                        "flags": {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "enum": [
                                    "LOW_CONFIDENCE",
                                    "KECAMATAN_MISMATCH",
                                    "ADMINISTRATIVE_CHANGE",
                                    "PREFIX_VARIATION",
                                    "SPELLING_VARIATION",
                                    "BOUNDARY_CHANGE",
                                    "NAME_STANDARDIZATION",
                                    "IMPLICIT_EVIDENCE",
                                    "MULTI_LEVEL_CORRECTION",
                                    "STRONG_REFERENCE",
                                    "WEAK_REFERENCE"
                                ]
                            }
                        },
                        "evidence_type": {
                            "type": "string",
                            "enum": ["EXPLICIT", "IMPLICIT", "PATTERN"]
                        }
                    },
                    "required": [
                        "original_pos_data", "corrections", "references",
                        "flags", "evidence_type"
                    ],
                    "additionalProperties": False
                }
            }
        },
        "required": ["corrections"]
    }


def format_dataframe_for_llm(df: pl.DataFrame, label: str, max_rows: int = 100) -> str:
    """Format Polars DataFrame as markdown table for LLM consumption."""
    if len(df) == 0:
        return f"**{label}**: No records"

    # Limit rows to avoid token limits
    df_sample = df.head(max_rows)
    truncated = len(df) > max_rows

    # Strip leading numbers from name columns to prevent LLM from seeing them
    if "Detail Records" in label:
        columns_to_strip = ["detail_kelurahan_desa"]
    elif "POS Records" in label:
        columns_to_strip = ["desa_kelurahan", "kecamatan", "kabupaten_kota_source"]
    else:
        columns_to_strip = []

    for col in columns_to_strip:
        if col in df_sample.columns:
            df_sample = df_sample.with_columns(
                pl.col(col).str.replace(r'^\d+\s*', '', literal=False)
            )

    # Convert to markdown table
    table = df_sample.to_pandas().to_markdown(index=False)

    result = f"**{label}** ({len(df)} total records"
    if truncated:
        result += f", showing first {max_rows}"
    result += "):\n\n" + table

    return result


def build_user_prompt(
    unmapped_detail: pl.DataFrame,
    unmapped_pos: pl.DataFrame,
    province: str
) -> str:
    """Build simplified user prompt with essential instructions."""

    # Read the template from markdown file
    prompt_path = Path(__file__).parent / "prompt" / "user_prompt.md"
    with open(prompt_path, 'r', encoding='utf-8') as f:
        template = f.read()

    # Format data tables
    detail_columns = [
        "detail_provinsi", "detail_kabupaten_kota", "detail_kecamatan",
        "detail_kode_kelurahan", "detail_kelurahan_desa", "detail_keterangan"
    ]
    detail_subset = unmapped_detail.select([col for col in detail_columns if col in unmapped_detail.columns])

    # Remove kecamatan hints formatting as it's no longer needed
    if 'potential_kecamatan_matches' in detail_subset.columns:
        detail_subset = detail_subset.drop('potential_kecamatan_matches')

    detail_table = format_dataframe_for_llm(detail_subset, "Unmapped Detail Records (Official Government Data)")

    # Format POS records
    pos_columns = [
        "kodepos", "desa_kelurahan", "kecamatan",
        "kabupaten_kota_source", "provinsi"
    ]
    pos_subset = unmapped_pos.select([col for col in pos_columns if col in unmapped_pos.columns])
    pos_table = format_dataframe_for_llm(pos_subset, "Unmapped POS Records (Outdated Postal Data)")

    data_tables = f"\n{detail_table}\n\n{pos_table}"

    # Replace placeholders in template
    prompt = template.replace("{province}", province.replace('_', ' ').title())
    prompt = prompt.replace("{data_tables}", data_tables)

    return prompt


def build_complete_prompt(
    unmapped_detail: pl.DataFrame,
    unmapped_pos: pl.DataFrame,
    province: str
) -> tuple[str, str, dict]:
    """
    Build complete simplified prompt for LLM correction generation.

    Returns:
        Tuple of (system_prompt, user_prompt, output_schema)
    """
    system_prompt = build_system_prompt()
    examples = build_examples_context()
    system_prompt += f"\n\n{examples}"  # Inject examples into system prompt

    user_prompt = build_user_prompt(unmapped_detail, unmapped_pos, province)
    output_schema = build_output_schema()

    return system_prompt, user_prompt, output_schema


