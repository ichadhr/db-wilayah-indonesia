"""
JSON Output Handler for POS Data Corrections.

Handles structured JSON output for correction rules that can be programmatically
applied or integrated into automated systems.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any


def validate_correction(correction: dict[str, Any]) -> bool:
    """Validate that a correction dict has all required fields."""
    required_fields = [
        "province", "regency_city", "field", "source",
        "original_value", "corrected_value", "references",
        "reasoning", "confidence", "flags"
    ]
    return all(field in correction for field in required_fields)


def categorize_corrections(corrections: list[dict[str, Any]], threshold: float = 0.80) -> dict[str, Any]:
    """Categorize corrections by confidence level."""
    high_confidence = [c for c in corrections if c.get("confidence", 0.0) >= threshold]
    low_confidence = [c for c in corrections if c.get("confidence", 0.0) < threshold]
    
    return {
        "high_confidence": high_confidence,
        "low_confidence": low_confidence,
        "total_corrections": len(corrections),
        "high_confidence_count": len(high_confidence),
        "low_confidence_count": len(low_confidence)
    }


def build_json_output(
    province: str,
    corrections: list[dict[str, Any]],
    confidence_threshold: float = 0.80
) -> dict[str, Any]:
    """
    Build structured JSON output for corrections.
    
    Args:
        province: Province name
        corrections: List of correction dictionaries
        confidence_threshold: Threshold for high/low confidence categorization
        
    Returns:
        Structured JSON-compatible dictionary
    """
    # Validate all corrections
    valid_corrections = [c for c in corrections if validate_correction(c)]
    if len(valid_corrections) < len(corrections):
        invalid_count = len(corrections) - len(valid_corrections)
        print(f"Warning: {invalid_count} corrections failed validation and were excluded")
    
    # Add sequential IDs
    for idx, correction in enumerate(valid_corrections, start=1):
        correction["id"] = idx
    
    # Categorize by confidence
    categorization = categorize_corrections(valid_corrections, confidence_threshold)
    
    # Build output structure
    output = {
        "metadata": {
            "province": province,
            "province_display": province.replace('_', ' ').title(),
            "generated_at": datetime.now().isoformat(),
            "generator": "LLM Correction System",
            "version": "1.0.0",
            "confidence_threshold": confidence_threshold
        },
        "summary": {
            "total_corrections": categorization["total_corrections"],
            "high_confidence": categorization["high_confidence_count"],
            "low_confidence": categorization["low_confidence_count"]
        },
        "corrections": valid_corrections
    }
    
    return output


def save_json_output(
    province: str,
    corrections: list[dict[str, Any]],
    output_dir: Path,
    confidence_threshold: float = 0.80
) -> Path:
    """
    Save corrections as JSON file.
    
    Args:
        province: Province name
        corrections: List of correction dictionaries
        output_dir: Output directory for JSON file
        confidence_threshold: Threshold for high/low confidence categorization
        
    Returns:
        Path to saved JSON file
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{province}_corrections.json"
    
    json_data = build_json_output(province, corrections, confidence_threshold)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(json_data, f, ensure_ascii=False, indent=2)
    
    return output_path


def load_json_corrections(json_path: Path) -> dict[str, Any]:
    """
    Load corrections from JSON file.
    
    Args:
        json_path: Path to JSON corrections file
        
    Returns:
        Parsed JSON data
    """
    with open(json_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def export_corrections_to_csv(
    corrections: list[dict[str, Any]],
    output_path: Path
) -> None:
    """
    Export corrections to CSV format for diagnostic purposes.

    Args:
        corrections: List of correction dictionaries
        output_path: Path to output CSV file
    """
    import polars as pl

    if not corrections:
        print("No corrections to export")
        return

    # Flatten nested data for CSV compatibility
    flattened_corrections = []
    for correction in corrections:
        flat_correction = correction.copy()
        # Convert flags list to comma-separated string
        if "flags" in flat_correction and isinstance(flat_correction["flags"], list):
            flat_correction["flags"] = ", ".join(flat_correction["flags"])
        flattened_corrections.append(flat_correction)

    # Convert to Polars DataFrame
    df = pl.DataFrame(flattened_corrections)

    # Reorder columns for readability
    column_order = [
        "id", "province", "regency_city", "field", "source",
        "original_value", "corrected_value", "confidence",
        "flags", "reasoning", "references"
    ]
    existing_columns = [col for col in column_order if col in df.columns]
    df = df.select(existing_columns)

    # Save to CSV
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.write_csv(output_path)
