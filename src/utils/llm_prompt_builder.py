"""
Prompt Engineering Utilities for LLM-based Postal Code Correction.

This module builds prompts for LLM analysis of unmapped postal code records,
including context injection, examples, and output schema definition.
"""

import json
from typing import Any

import polars as pl


def build_system_prompt() -> str:
    """Build system prompt defining LLM role and expertise."""
    return """You are an expert in Indonesian administrative divisions and postal code systems. Your task is to analyze unmapped postal code records and identify corrections based on:

1. **Context Clues**: The `detail_keterangan` field contains crucial information about:
   - Name changes (e.g., "Perubahan nama desa semula Kisam menjadi Kuta Buluh")
   - Administrative relocations (e.g., "pemekaran", "perubahan batas")
   - Official references (Surat, Qanun, Keputusan)

2. **Kecamatan Hints**: The `potential_kecamatan_matches` column provides high-similarity kecamatan matches from POS data (similarity > 0.8). Use these when kecamatan similarity is high but kelurahan similarity is low, as they may indicate the same administrative area despite name variations or kelurahan/desa differences.
   - Example: POS kecamatan "Indra Jaya" (similarity 1.0) vs detail kecamatan "Indrajaya" with low kelurahan match - consider administrative relationship confirmed despite kelurahan name variations.
   
3. **Naming Patterns**: Common inconsistencies include:
   - Prefix variations: "Meunasah X" vs "X", "Kampong Y" vs "Y", "Kp. Z" vs "Z"
   - Spelling differences: "Indra Jaya" vs "Indrajaya"
   - Historical names vs current official names

4. **Gate System Rules**: Matches must satisfy hierarchical similarity thresholds:
   - Province: ≥ 0.95
   - Kabupaten/Kota: ≥ 0.95
   - Kecamatan: ≥ 0.75
   - Kelurahan/Desa: ≥ 0.70
   - Overall weighted score: ≥ 0.80

**Special Cases**:
- If `detail_keterangan` explicitly mentions kecamatan relocation, the kecamatan gate can be overridden
- Consider `potential_kecamatan_matches` when evaluating corrections - high similarity (>0.8) may indicate the same location
- Always prioritize official government documentation over POS data
- Flag any matches where kecamatan names differ significantly

**CRITICAL - Multi-Level Analysis**:
You MUST systematically check for corrections at ALL administrative levels:
- kabupaten_kota (regency/city level)
- kecamatan (district level) 
- desa_kelurahan (village level)

Do NOT focus only on desa_kelurahan! Kecamatan and kabupaten_kota corrections are equally important.

Your output must be structured JSON following the exact schema provided."""


def build_examples_context() -> str:
    """Build examples from Aceh province corrections."""
    return """**Example Corrections (Aceh Province)**:

1. **Name Change with Official Reference**:
   - Original (POS): "Kisam"
   - Corrected: "Kuta Buluh"
   - Context: "Perubahan nama desa semula Kisam menjadi Kuta Buluh"
   - References: "Surat Dirjen Bina Pemdes No. 100.3.3.1/1952/BPD tanggal 12 Mei 2023"
   - Confidence: 0.95 (explicit name change documented)

2. **Prefix Addition Pattern**:
   - Original (POS): "Jareng"
   - Corrected: "Meunasah Jareng"
   - Context: Official documentation shows standardization
   - References: "surat Bupati Pidie No 140/2364 tanggal 13 April 2021"
   - Confidence: 0.85 (common pattern, well-documented)

3. **Prefix Removal Pattern**:
   - Original (POS): "Kampong Panjoe"
   - Corrected: "Panjoe"
   - Context: Standardization to remove "Kampong" prefix
   - References: "surat Bupati Pidie No 140/2364 tanggal 13 April 2021"
   - Confidence: 0.85 (common pattern, well-documented)

4. **Low Confidence - Kecamatan Mismatch**:
   - Original (POS): "Ara"
   - Corrected: "Meunasah Ara"
   - Context: POS kecamatan is "Bandar Baru" vs detail "Kembang Tanjong"
   - References: "Surat Pem Aceh No. 146.1/10560 tanggal 13 Juni 2016"
   - Confidence: 0.75 (kecamatan mismatch requires verification)
   - Flags: ["LOW_CONFIDENCE", "KECAMATAN_MISMATCH"]

5. **Kecamatan-Level Correction**:
   - Field: "kecamatan" (NOT desa_kelurahan)
   - Original (POS): "Indra Jaya"
   - Corrected: "Indrajaya"
   - Context: Spelling standardization - space removed
   - References: "1. Surat Pem Aceh No. 146.1/10560 tgl 13 Juni 2016; 2. Surat Bupati Pidie No 140/2364 tgl 13 April 2021; 3. Surat Sesditjen Bina Pemerintahan Desa No 145/2430/BPD tgl 24 Mei 2021"
   - Confidence: 0.90 (well-documented spelling correction)
   - Flags: ["SPELLING_VARIATION"]

**IMPORTANT**: Always check for corrections at ALL administrative levels - kabupaten_kota, kecamatan, AND desa_kelurahan!
"""


def build_output_schema() -> dict[str, Any]:
    """Build JSON schema for LLM output."""
    return {
        "type": "object",
        "properties": {
            "corrections": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "province": {"type": "string"},
                        "regency_city": {"type": "string"},
                        "field": {
                            "type": "string",
                            "enum": ["desa_kelurahan", "kecamatan", "kabupaten_kota"]
                        },
                        "source": {"type": "string", "const": "POS Data"},
                        "original_value": {"type": "string"},
                        "corrected_value": {"type": "string"},
                        "references": {"type": "string"},
                        "reasoning": {"type": "string"},
                        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                        "flags": {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "enum": [
                                    "LOW_CONFIDENCE",
                                    "KECAMATAN_MISMATCH",
                                    "ADMINISTRATIVE_CHANGE",
                                    "PREFIX_VARIATION",
                                    "SPELLING_VARIATION"
                                ]
                            }
                        }
                    },
                    "required": [
                        "province", "regency_city", "field", "source",
                        "original_value", "corrected_value", "references",
                        "reasoning", "confidence", "flags"
                    ]
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
    """Build user prompt with unmapped records for analysis."""

    # Format detail records (with keterangan)
    detail_columns = [
        "detail_provinsi", "detail_kabupaten_kota", "detail_kecamatan",
        "detail_kode_kelurahan", "detail_kelurahan_desa", "detail_keterangan",
        "potential_kecamatan_matches"
    ]
    detail_subset = unmapped_detail.select([col for col in detail_columns if col in unmapped_detail.columns])

    # Format kecamatan hints for better readability in the table
    if 'potential_kecamatan_matches' in detail_subset.columns:
        detail_subset = detail_subset.with_columns(
            pl.col('potential_kecamatan_matches').map_elements(
                lambda x: format_kecamatan_hints_for_prompt(str(x)) if x else "",
                return_dtype=pl.Utf8
            ).alias('potential_kecamatan_matches')
        )

    detail_table = format_dataframe_for_llm(detail_subset, "Unmapped Detail Records (Official Government Data)")

    # Format POS records
    pos_columns = [
        "kodepos", "desa_kelurahan", "kecamatan",
        "kabupaten_kota", "provinsi"
    ]
    pos_subset = unmapped_pos.select([col for col in pos_columns if col in unmapped_pos.columns])
    pos_table = format_dataframe_for_llm(pos_subset, "Unmapped POS Records (Outdated Postal Data)")

    prompt = f"""**Province**: {province.replace('_', ' ').title()}

**Task**: Analyze the following unmapped records and identify corrections where POS data names need to be updated to match official government records.

{detail_table}

{pos_table}

**Instructions**:
1. **SYSTEMATICALLY CHECK ALL ADMINISTRATIVE LEVELS**:
   - Kabupaten/Kota inconsistencies (field: "kabupaten_kota")
   - Kecamatan inconsistencies (field: "kecamatan")
   - Kelurahan/Desa inconsistencies (field: "desa_kelurahan")
   
2. Look for matches between Detail and POS records based on `detail_keterangan` clues

3. Apply gate system rules (but override kecamatan gate if keterangan indicates relocation)

4. Extract official references from `detail_keterangan` (Surat, Qanun, Keputusan)

5. Assign confidence scores:
   - 0.90-1.0: Explicit name change with clear documentation
   - 0.80-0.89: Strong pattern match with documentation
   - 0.70-0.79: Reasonable match but needs verification
   - Below 0.70: Do not include (too uncertain)
   
6. Flag low-confidence matches and special cases (kecamatan mismatches, etc.)

**CRITICAL**: Do NOT only focus on desa_kelurahan corrections. Check kecamatan and kabupaten_kota fields too!

**Output**: Return a JSON object with array of corrections following the exact schema."""

    # Enhance prompt with kecamatan hints if available
    enhanced_prompt = enhance_llm_prompt_with_kecamatan_hints(prompt, unmapped_detail)

    return enhanced_prompt


def build_complete_prompt(
    unmapped_detail: pl.DataFrame,
    unmapped_pos: pl.DataFrame,
    province: str
) -> tuple[str, str, dict]:
    """
    Build complete prompt for LLM correction generation.

    Returns:
        Tuple of (system_prompt, user_prompt, output_schema)
    """
    system_prompt = build_system_prompt()
    user_prompt = build_user_prompt(unmapped_detail, unmapped_pos, province)
    output_schema = build_output_schema()

    return system_prompt, user_prompt, output_schema


# ============================================================================
# LLM PROMPT ENHANCEMENT FUNCTIONS
# ============================================================================

def format_kecamatan_hints_for_prompt(hints_str: str) -> str:
    """
    Format kecamatan hints for inclusion in LLM prompt.

    Args:
        hints_str: Formatted string of kecamatan hints (e.g., "Indra Jaya (1.0); Bandar Dua (0.91)")

    Returns:
        Formatted text for LLM prompt
    """
    if not hints_str or hints_str.strip() == '':
        return ""

    formatted = "\n**Potential Kecamatan Matches:**\n"
    # Split by semicolon and format each hint
    hints = [h.strip() for h in hints_str.split(';') if h.strip()]
    for hint in hints:
        formatted += f"- {hint}\n"

    return formatted


def enhance_llm_prompt_with_kecamatan_hints(
    base_prompt: str,
    detail_df: pl.DataFrame
) -> str:
    """
    Enhance LLM prompt with kecamatan similarity hints.

    Args:
        base_prompt: Original LLM prompt
        detail_df: Detail dataframe with kecamatan hints column

    Returns:
        Enhanced prompt with kecamatan context
    """
    # Check if any records have kecamatan hints
    has_hints = (
        'potential_kecamatan_matches' in detail_df.columns and
        detail_df['potential_kecamatan_matches'].is_not_null().any()
    )

    if not has_hints:
        return base_prompt

    # Add kecamatan hints instruction
    enhancement = """
**Kecamatan Similarity Context:**
Some records include potential kecamatan matches from POS data with high similarity scores (>0.8).
Consider these when evaluating corrections - they may indicate the same administrative area
despite different name spellings or kelurahan/desa variations.

"""

    return base_prompt + enhancement
