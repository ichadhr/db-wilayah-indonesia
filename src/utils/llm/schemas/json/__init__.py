"""
JSON Schema module for LLM output handling.

Provides structured JSON output generation and validation for POS data corrections.
"""

from .json_schema import (
    build_json_output,
    categorize_corrections,
    export_corrections_to_csv,
    load_json_corrections,
    save_json_output,
    validate_correction,
)

__all__ = [
    "build_json_output",
    "categorize_corrections",
    "export_corrections_to_csv",
    "load_json_corrections",
    "save_json_output",
    "validate_correction",
]
