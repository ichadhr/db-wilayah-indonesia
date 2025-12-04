"""
Markdown Report Generator for POS Data Corrections.

Generates human-readable markdown documentation following the exact format from
docs/pos_data_correction_process.md and src/datas/comparing_pos/aceh.md.
"""

from datetime import datetime
from pathlib import Path
from typing import Any
import re

import polars as pl


def escape_markdown(text: str) -> str:
    """Escape special markdown characters in text."""
    if not text:
        return ""
    # Don't escape if it's already formatted content
    return text


def format_confidence_flag(confidence: float, flags: list[str], references: str) -> str:
    """Format references with confidence flag if low confidence."""
    if confidence < 0.80:
        flag_icon = "⚠️"
        flag_text = f"{flag_icon} Confidence: {confidence:.2f} - "
        return flag_text + references
    return references


def generate_corrections_table(corrections: list[dict[str, Any]]) -> str:
    """Generate markdown table for corrections."""
    if not corrections:
        return "*No corrections identified.*\n"
    
    table_header = """| No | Province | Regency/City | Field | Source | Original Value | Corrected Value | References |
| --- | --- | --- | --- | --- | --- | --- | --- |
"""
    
    rows = []
    for idx, correction in enumerate(corrections, start=1):
        # Format references with confidence flag
        references = format_confidence_flag(
            correction.get("confidence", 0.0),
            correction.get("flags", []),
            correction.get("references", "")
        )
        
        # Add note for special cases in references
        if "KECAMATAN_MISMATCH" in correction.get("flags", []):
            if "note:" not in references.lower():
                references += f" (Note: {correction.get('reasoning', 'Kecamatan mismatch detected')})"
        
        row = (
            f"| {idx} "
            f"| {escape_markdown(correction.get('province', ''))} "
            f"| {escape_markdown(correction.get('regency_city', ''))} "
            f"| {escape_markdown(correction.get('field', ''))} "
            f"| {escape_markdown(correction.get('source', 'POS Data'))} " 
            f"| {escape_markdown(correction.get('original_value', ''))} "
            f"| {escape_markdown(correction.get('corrected_value', ''))} "
            f"| {escape_markdown(references)} |"
        )
        rows.append(row)
    
    return table_header + "\n".join(rows) + "\n"


def generate_unmapped_detail_table(unmapped_detail: pl.DataFrame) -> str:
    """Generate markdown table for remaining unmapped detail records."""
    if len(unmapped_detail) == 0:
        return "*All detail records have been matched.*\n"
    
    table_header = """| No | Province | Regency/City | Kecamatan | Kode Kelurahan | Kelurahan/Desa | Keterangan |
| --- | --- | --- | --- | --- | --- | --- |
"""
    
    rows = []
    for idx, row in enumerate(unmapped_detail.iter_rows(named=True), start=1):
        table_row = (
            f"| {idx} "
            f"| {escape_markdown(row.get('detail_provinsi', ''))} "
            f"| {escape_markdown(row.get('detail_kabupaten_kota', ''))} "
            f"| {escape_markdown(row.get('detail_kecamatan', ''))} "
            f"| {escape_markdown(row.get('detail_kode_kelurahan', ''))} "
            f"| {escape_markdown(row.get('detail_kelurahan_desa', ''))} "
            f"| {escape_markdown(row.get('detail_keterangan', ''))} |"
        )
        rows.append(table_row)
    
    return table_header + "\n".join(rows) + "\n"


def generate_unmapped_pos_table(unmapped_pos: pl.DataFrame) -> str:
    """Generate markdown table for remaining unmapped POS records."""
    if len(unmapped_pos) == 0:
        return "*All POS records have been matched.*\n"
    
    table_header = """| No | Kode Pos | Province | Regency/City | Kecamatan | Kelurahan/Desa |
| --- | --- | --- | --- | --- | --- |
"""
    
    rows = []
    for idx, row in enumerate(unmapped_pos.iter_rows(named=True), start=1):
        table_row = (
            f"| {idx} "
            f"| {escape_markdown(str(row.get('kodepos', '')))} "
            f"| {escape_markdown(row.get('provinsi', ''))} "
            f"| {escape_markdown(row.get('kabupaten_kota', ''))} "
            f"| {escape_markdown(row.get('kecamatan', ''))} "
            f"| {escape_markdown(row.get('desa_kelurahan', ''))} |"
        )
        rows.append(table_row)
    
    return table_header + "\n".join(rows) + "\n"


def generate_markdown_report(
    province: str,
    corrections: list[dict[str, Any]],
    unmapped_detail: pl.DataFrame | None = None,
    unmapped_pos: pl.DataFrame | None = None,
    output_path: Path | None = None
) -> str:
    """
    Generate complete markdown report following official format.
    
    Args:
        province: Province name
        corrections: List of correction dictionaries
        unmapped_detail: Optional DataFrame of remaining unmapped detail records
        unmapped_pos: Optional DataFrame of remaining unmapped POS records
        output_path: Optional path to save the markdown file
        
    Returns:
        Generated markdown content as string
    """
    province_title = province.replace('_', ' ').title()
    
    # Build markdown content
    markdown = f"""# POS Data Corrections for {province_title}

## Overview
This document tracks corrections applied to POS (Pos Indonesia) data for {province_title} province, focusing on specific naming inconsistencies identified during data matching processes.

## Corrections Table

{generate_corrections_table(corrections)}
"""
    
    # Filter unmapped_detail to exclude records that now have corrections
    # A detail record should be removed from "unmapped" only if its specific name
    # appears as the corrected_value in a correction (meaning POS was updated to match it)
    if unmapped_detail is not None and len(corrections) > 0:
        # Build set of corrected values per field type
        corrected_kelurahan = {
            (c.get('province', ''), c.get('regency_city', ''), c.get('corrected_value', ''))
            for c in corrections if c.get('field') == 'desa_kelurahan'
        }
        corrected_kecamatan = {
            (c.get('province', ''), c.get('regency_city', ''), c.get('corrected_value', ''))
            for c in corrections if c.get('field') == 'kecamatan'
        }
        corrected_kabupaten = {
            (c.get('province', ''), c.get('corrected_value', ''))
            for c in corrections if c.get('field') == 'kabupaten_kota'
        }
        
        # Only filter if we have corrections
        if corrected_kelurahan or corrected_kecamatan or corrected_kabupaten:
            def normalize_name(name: str) -> str:
                return re.sub(r'^\d+\s*', '', name)

            # Filter out detail records that now have matches
            def is_corrected(row: dict) -> bool:
                prov = row.get('detail_provinsi', '')
                reg = normalize_name(row.get('detail_kabupaten_kota', ''))
                kel = normalize_name(row.get('detail_kelurahan_desa', ''))
                kec = normalize_name(row.get('detail_kecamatan', ''))

                # Check if this detail record's name matches any corrected value
                return (
                    (prov, reg, kel) in corrected_kelurahan or
                    (prov, reg, kec) in corrected_kecamatan or
                    (prov, reg) in corrected_kabupaten
                )
            
            unmapped_detail = unmapped_detail.filter(
                ~pl.struct(['detail_provinsi', 'detail_kabupaten_kota', 'detail_kelurahan_desa', 'detail_kecamatan'])
                .map_elements(is_corrected, return_dtype=pl.Boolean)
            )

    # Add remaining unmapped records section if provided
    if unmapped_detail is not None:
        markdown += """
## Remaining Unmapped Records

After applying the above corrections, the following records remain unmapped and may require further analysis or data updates.

"""
        
        markdown += """### Unmapped Detail Records
These official government records could not be matched to POS data:

"""
        markdown += generate_unmapped_detail_table(unmapped_detail)
    
    # Add footer with generation timestamp
    markdown += f"""
---
*Generated by LLM Correction System on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*
"""
    
    # Save to file if path provided
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(markdown, encoding="utf-8")
    
    return markdown


def save_markdown_report(
    province: str,
    corrections: list[dict[str, Any]],
    output_dir: Path,
    unmapped_detail: pl.DataFrame | None = None,
    unmapped_pos: pl.DataFrame | None = None
) -> Path:
    """
    Save markdown report to file.
    
    Args:
        province: Province name
        corrections: List of correction dictionaries
        output_dir: Output directory for markdown file
        unmapped_detail: Optional DataFrame of remaining unmapped detail records
        unmapped_pos: Optional DataFrame of remaining unmapped POS records
        
    Returns:
        Path to saved markdown file
    """
    output_path = output_dir / f"{province}.md"
    generate_markdown_report(
        province=province,
        corrections=corrections,
        unmapped_detail=unmapped_detail,
        unmapped_pos=unmapped_pos,
        output_path=output_path
    )
    return output_path
