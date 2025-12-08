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

**DATA STRUCTURE - CRITICAL**:

Detail record columns:
- `detail_provinsi`, `detail_kabupaten_kota`, `detail_kecamatan`: Administrative hierarchy (CURRENT official names)
- `detail_kode_kelurahan`: Administrative code
- `detail_kelurahan_desa`: Village name (CURRENT official) - may have SEQUENCE number prefix (see below)
- `detail_keterangan`: Historical context - may reference OTHER records, do NOT assume applies to THIS row
- `potential_kecamatan_matches`: High-similarity kecamatan from POS data

POS record columns:
- `provinsi`, `kabupaten_kota`, `kecamatan`: Administrative hierarchy from POS data (use these for province, regency_city, district fields in corrections)
- `desa_kelurahan`: Village name from POS data
- `kodepos`: Postal code

**CRITICAL RULES & CONSTRAINTS**:
1. **Source of Truth**: Column values represent CURRENT official names.
2. **Sequence Numbers**: ALWAYS strip identifying number prefixes (e.g., "6 Lawe" -> "Lawe").
3. **Target Verification**: If 'keterangan' says "X to Y", Y MUST match the current 'detail' value. If not, SKIP the record.
4. **Existence Check**: Only correct if the old name (X) actually exists in the POS data.
5. **NO-OP Check**: If Corrected Value == Original Value (case-insensitive), DO NOT generate a record.
6. **Evidence Requirement**: Do NOT infer changes. Only correct if 'detail_keterangan' or official documents explicitly support it.
7. **Explicit Reference Constraint**: You only generate corrections when the `detail_keterangan` field explicitly mentions or references the specific change relevant to the current row's `detail_kelurahan_desa` or other target fields. If the keterangan does not mention the row's values (e.g., does not reference "Lawe Perbunga" in the text), you must skip generating corrections for that row.

**WHAT NOT TO DO (Negative Constraints)**:
- Do NOT correct spelling differences unless explicitly documented.
- Do NOT assume a record applies to this row if the target name doesn't match.
- Do NOT include "administrative change" as a flag without a specific decree/surat reference.

**MULTIPLE CORRECTIONS PER RECORD**:
Administrative changes can affect multiple hierarchy levels simultaneously. When a single detail record describes a complex change (like village relocation), you MAY generate multiple corrections for different fields (desa_kelurahan, kecamatan, kabupaten_kota) if:
- All corrections reference the SAME administrative change event
- Each correction has independent justification
- The changes are logically connected (e.g., village relocation implies kecamatan change)
- Each correction cites specific aspects of the reference documents

**Example of Valid Multiple Corrections (Aceh Case)**:
Detail record: kecamatan="Indrajaya", kelurahan_desa="Peutoe", keterangan="Surat Pem Aceh No. 146.1/10560..."
- Correction 1: kecamatan "Indra Jaya" → "Indrajaya" (spelling correction)
- Correction 2: desa_kelurahan "Putoe Gapui" → "Peutoe" (official name change)
Both corrections justified by same official decree documents.

**Output Format Requirements**:
- **Reasoning**: Must be EVIDENCE-BASED. State the specific change type (relocation/renaming) and the document type.
- **References**: Join multiple sources with semicolons (;).
- **JSON**: Valid, parseable JSON only.

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

4. **Kecamatan-Level Correction**:
   - Field: "kecamatan" (NOT desa_kelurahan)
   - Original (POS): "Indra Jaya"
   - Corrected: "Indrajaya"
   - Context: Spelling standardization - space removed
   - Confidence: 0.90 (well-documented spelling correction)
   - Flags: ["SPELLING_VARIATION"]

5. **CRITICAL - Verify Keterangan Matches Current Name**:
   
   Row A: kelurahan="6 Lawe Perbunga", keterangan="Lawe Sagu Baru menjadi Pangguh"
   - Current name = "Lawe Perbunga" (strip "6 ")
   - Keterangan says "→ Pangguh" but "Pangguh" ≠ "Lawe Perbunga"
   - Result: **SKIP** - this keterangan is for a DIFFERENT record
   
   Row B: kelurahan="20 Pangguh", keterangan="Lawe Sagu Baru menjadi Pangguh"
   - Current name = "Pangguh" (strip "20 ")
   - Keterangan says "→ Pangguh" = "Pangguh" ✓
   - Check POS: "Lawe Sagu Baru" exists in matching kecamatan? YES
   - Result: Generate correction Lawe Sagu Baru → Pangguh

6. **Number Prefix Stripping (Bali Example)**:
   - detail_kelurahan_desa: "2 Dapdap Putih"
   - keterangan: "Perubahan nama desa semula Tista menjadi Dapdap Putih"
   - Current name = "Dapdap Putih" (strip "2 ")
   - Keterangan says "→ Dapdap Putih" = "Dapdap Putih" ✓
   - Result: Generate correction Tista → Dapdap Putih (NOT "2 Dapdap Putih")

**IMPORTANT**: Always verify keterangan target matches current column value before generating correction!
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

**Task**: Analyze the following unmapped records and identify corrections where POS data names need to be updated to match official government records. A single record may generate MULTIPLE corrections when administrative changes affect multiple hierarchy levels.

{detail_table}

{pos_table}

**Instructions**:
1. **HIERARCHY CHECK**: systematically evaluate Kabupaten -> Kecamatan -> Desa/Kelurahan.

2. **MATCHING LOGIC**:
    - Use `detail_keterangan` as the primary key for matching.
    - Override fuzzy similarity gates IF 'keterangan' explicitly describes a relocation/change.

3. **VALIDATION**:
    - Verify that the administrative change described actually applies to THIS specific row (target name check).

4. **MULTIPLE CORRECTIONS**:
    - When a single administrative change affects multiple levels, generate separate corrections for each affected field.
    - Each correction must be independently justified.

5. **FIELD POPULATION FROM POS DATA**:
    - Set `province` to the corresponding POS record's `provinsi`
    - Set `regency_city` to the corresponding POS record's `kabupaten_kota`
    - Set `district` to the corresponding POS record's `kecamatan`
    - These fields must come from POS data, not detail data.

6. **CONFIDENCE SCORING**:
    - 0.9-1.0: Explicit Change (e.g., "X menjadi Y" with matching Decree).
    - 0.8-0.9: Standardized Pattern (e.g., Prefix addition "Meunasah X").
    - < 0.7: SKIP.

7. **OUTPUT**:
    - Return valid JSON array.
    - NO markdown fencing around the JSON.

**CRITICAL**: Do NOT only focus on desa_kelurahan corrections. Check kecamatan and kabupaten_kota fields too! Administrative relocations may require corrections at multiple levels.

**VALID MULTIPLE CORRECTIONS EXAMPLE**:
Record has changes in both kecamatan spelling and village name:
- Correction 1: kecamatan "Indra Jaya" → "Indrajaya"
- Correction 2: desa_kelurahan "Putoe Gapui" → "Peutoe"

**Output**: Return a JSON object with array of corrections following the exact schema. Multiple corrections per record are allowed when justified by the same administrative change."""

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
