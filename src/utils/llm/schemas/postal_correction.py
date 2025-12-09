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
    return """You are an expert in Indonesian administrative divisions and postal code systems. Your task is to analyze unmapped postal code records and identify corrections based on evidence.

**CORE PROCESSING RULES**:
1. **Evidence Requirement**: Only correct if `detail_keterangan` explicity mentions the change.
2. **Target Verification**: keterangan target MUST match current `detail_kelurahan_desa` value.
3. **Sequence Stripping**: ALWAYS strip number prefixes (e.g., "6 Lawe" -> "Lawe") before comparison.
4. **Hierarchical Gates**: Province ≥0.95, Kabupaten/Kota ≥0.95, Kecamatan ≥0.75, Kelurahan ≥0.70.
5. **Confidence Thresholds**: 0.9-1.0 for explicit changes, 0.8-0.9 for patterns, <0.7 skip.
6. **Correction Limits**: Maximum 3 corrections per record.
7. **Field Priority**: desa_kelurahan > kecamatan > kabupaten_kota.

**VALIDATION SEQUENCE**:
1. Verify keterangan matches current row value (current name must match "from" part of change).
2. Check POS data exists for the old name.
3. Confirm hierarchical consistency.
4. Apply confidence scoring.
5. Generate justified corrections.

**WHAT TO AVOID**:
- No spelling corrections without documentation.
- No assumptions about record applicability (target name mismatch = SKIP).
- No redundant corrections (original = corrected).
- No over-generation beyond evidence.

Your output must be structured JSON following the exact schema provided."""


def build_examples_context() -> str:
    """Build diverse regional examples for context."""
    return """
**Example Corrections Across Regions**:

**1. ACEH - Name Change with Official Reference**:
    - Original (POS): "Kisam"
    - Corrected: "Kuta Buluh"
    - Context: "Perubahan nama desa semula Kisam menjadi Kuta Buluh"
    - References: "Surat Dirjen Bina Pemdes No. 100.3.3.1/1952/BPD"
    - Confidence: 0.95 (explicit decree)

**2. JAVA (West Java) - Kecamatan Boundary Change**:
    - Field: "kecamatan"
    - Original (POS): "Suranenggala"
    - Corrected: "Gunung Jati"
    - Context: Administrative boundary adjustment in Kabupaten Cirebon
    - References: "Perda Kabupaten Cirebon No 18/2007; Surat Sekda No 130/2972/PemKsm tgl 2 Juli 2020"
    - Confidence: 0.92 (official decree with multiple references)

**3. JAVA (West Java) - Desa/Kelurahan Name Change**:
    - Field: "desa_kelurahan"
    - Original (POS): "Sirnasari"
    - Corrected: "Jatinunggal"
    - Context: Official name change in Kabupaten Sumedang
    - References: "Perda Kabupaten Sumedang No. 2 Tahun 2024; Surat Rekomendasi Ditjen Pemdes No. 100.3.3.1/5293/BPD tanggal 16 Oktober 2024"
    - Confidence: 0.94 (recent official decree)

**4. KALIMANTAN TENGAH - Administrative Relocation**:
    - Field: "desa_kelurahan"
    - Original (POS): "Kahayan Hilir"
    - Corrected: "Pulang Pisau"
    - Context: Village relocation affecting administrative boundaries
    - References: "UU No 5/2002; Surat Bup No 100/18/PEMPP/I/2020 tgl 28 Januari 2020"
    - Confidence: 0.91 (law and official decree)

**5. BALI - Sequence Number Handling**:
    - detail_kelurahan_desa: "2 Dapdap Putih"
    - keterangan: "Perubahan nama desa semula Tista menjadi Dapdap Putih"
    - Current name: "Dapdap Putih" (strip "2 ")
    - POS check: "Tista" exists -> Generate correction
    - Confidence: 0.90 (explicit name change)

**6. ACEH - Multiple Corrections from Same Decree**:
    Administrative change affecting both kecamatan and desa/kelurahan levels:
    - Correction 1: kecamatan "Indra Jaya" -> "Indrajaya" (spelling standardization)
    - Correction 2: desa_kelurahan "Putoe Gapui" -> "Peutoe" (name change)
    - Same References: "Surat Pem Aceh No. 146.1/10560 tgl 13 Juni 2016; surat Bupati Pidie No 140/2364 tgl 13 April 2021; Surat Sesditjen Bina Pemerintahan Desa No 145/2430/BPD tgl 24 Mei 2021"
    - Confidence: 0.93 each (same administrative change event)

**7. SULAWESI TENGGARA - Multiple Corrections from Same Decree (Real Data)**:
    Administrative changes affecting both kecamatan and desa/kelurahan levels:
    - Correction 1: kecamatan "Kabawo" -> "Kontu Kowuna" (boundary change)
    - Correction 2: kecamatan "Tongkuno" -> "Tongkuno Selatan" (boundary change)
    - Correction 3: desa_kelurahan "Karoo" -> "Lembo" (name change)
    - Correction 4: desa_kelurahan "Katumpu" -> "Lawama" (name change)
    - Same decree reference: "Surat Bup Muna No 188/2304 tgl 1 November 2019; Perda No. 5/2008; Perda 12/2014"
    - Confidence: 0.95 each

**CRITICAL VALIDATION PATTERNS**:
- **Match Required**: keterangan target must equal current column value
- **POS Verification**: Old name must exist in POS data
- **Sequence Strip**: Always remove leading numbers before comparison
- **Skip if Invalid**: Better to skip than generate incorrect corrections
- **Reference Quality**: Prefer decrees with specific dates and numbers
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
                        "district": {"type": "string"},
                        "field": {
                            "type": "string",
                            "enum": ["desa_kelurahan", "kecamatan", "kabupaten_kota"]
                        },
                        "source": {"type": "string", "const": "POS Data"},
                        "original_value": {"type": "string", "description": "The OLD name from POS data"},
                        "corrected_value": {"type": "string", "description": "The CURRENT official name (number prefix stripped)"},
                        "references": {"type": "string", "description": "Official document references, semicolon-separated"},
                        "reasoning": {"type": "string", "description": "EVIDENCE-BASED explanation. Must explicitly state the type of change (e.g., 'Renaming', 'Relocation', 'Spelling Fix') and cite the 'keterangan' evidence. Format: '[Type] [Explanation]'. Max 150 chars."},
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
                        "province", "regency_city", "district", "field", "source",
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

    prompt = f"**Province**: {province.replace('_', ' ').title()}\n\n"

    # INSTRUCTIONS FIRST (Important for attention)
    prompt += """**Task**: Analyze unmapped records and identify corrections relative to POS data.

**Instructions**:
1. **HIERARCHY CHECK**: systematically evaluate Kabupaten -> Kecamatan -> Desa/Kelurahan.
2. **MATCHING LOGIC**: Use `detail_keterangan` as primary key...
3. **VALIDATION**: Verify administrative change applies to THIS row...
4. **MULTIPLE CORRECTIONS**: Allow when justified by same change event...
5. **FIELD POPULATION**: Set province/regency_city/district from POS data...

**CORRECTION LIMITS & DECISION TREE**:

Follow this decision process for EACH record:

1. **EVIDENCE CHECK**: Does `detail_keterangan` explicity reference this row's current name?
   - YES -> Continue to step 2
   - NO -> SKIP this record

2. **POS EXISTENCE**: Does the old name from keterangan exist in POS data?
   - YES -> Continue to step 3
   - NO -> SKIP this record

3. **HIERARCHICAL VALIDATION**: Check province/regency/district consistency
   - VALID -> Continue to step 4
   - INVALID -> SKIP this record

4. **CORRECTION GENERATION**: Generate 1-3 corrections maximum, prioritized by:
   - Priority 1: desa_kelurahan changes (highest impact)
   - Priority 2: kecamatan spelling/corrections
   - Priority 3: kabupaten_kota changes (rare)

**CRITICAL**: Do NOT focus only on desa_kelurahan. Check kecamatan and kabupaten_kota too!
"""

    # Data tables AFTER instructions
    
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

    prompt += f"\n{detail_table}\n\n{pos_table}"
    
    prompt += "\n\n**Output**: Return JSON object with corrections array following schema."

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
    examples = build_examples_context()
    system_prompt += f"\n\n{examples}"  # Inject examples into system prompt

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
