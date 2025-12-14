"""
Schemas module for LLM output formatting and validation.

This module provides schema definitions and output formatters for various
data formats used in the LLM correction system.

Submodules:
    - json: JSON schema and output handling for corrections
    - md: Markdown report generation for corrections
"""

from . import json, md

# Re-export commonly used functions from json submodule
from .json import (
    build_json_output,
    categorize_corrections,
    export_corrections_to_csv,
    load_json_corrections,
    save_json_output,
    validate_correction,
)

# Re-export commonly used functions from md submodule
from .md import (
    escape_markdown,
    format_confidence_flag,
    generate_corrections_table,
    generate_markdown_report,
    generate_skipped_corrections_table,
    generate_unmapped_detail_table,
    generate_unmapped_pos_table,
    save_markdown_report,
)

__all__ = [
    # Submodules
    "json",
    "md",
    # JSON functions
    "build_json_output",
    "categorize_corrections",
    "export_corrections_to_csv",
    "load_json_corrections",
    "save_json_output",
    "validate_correction",
    # Markdown functions
    "escape_markdown",
    "format_confidence_flag",
    "generate_corrections_table",
    "generate_skipped_corrections_table",
    "generate_unmapped_detail_table",
    "generate_unmapped_pos_table",
    "generate_markdown_report",
    "save_markdown_report",
]
