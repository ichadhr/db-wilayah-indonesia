# POS Data Correction Process

## Overview

This document outlines the manual process for correcting postal code data from Pos Indonesia (POS) to ensure consistency with official government administrative divisions. This process is essential for maintaining compliance with official ministerial decrees (such as Keputusan Menteri Dalam Negeri Nomor 300.2.2-2138 Tahun 2025) and creating accurate regional databases.

The process involves analyzing unmapped data from automated matching processes and manually identifying corrections based on official government documentation.

## Scope

This process applies to all 38 provinces in Indonesia. Each province requires individual analysis of its unmapped data files.

## Source Files

For each province, the following source files are used:

1. **`src/log/{province}/{province}_remain_unmapped_detail.csv`**
   - Contains official government detail data that couldn't be automatically matched
   - Columns: `detail_provinsi`, `detail_kabupaten_kota`, `detail_kecamatan`, `detail_kode_kelurahan`, `detail_kelurahan_desa`, `detail_keterangan`
   - The `detail_keterangan` column provides crucial clues for matching (e.g., name changes, relocations)

2. **`src/log/{province}/{province}_remain_unmapped_pos.csv`**
   - Contains unmapped POS postal code data
   - Columns: `kodepos`, `desa_kelurahan`, `kecamatan`, `kabupaten_kota`, `provinsi`, `kabupaten_kota_source`
   - Contains the original POS names that need correction

## Output File

**`src/datas/comparing_pos/{province}.md`**
- Markdown documentation file tracking all corrections applied
- Structured table format with official references
- Serves as audit trail and knowledge base for future corrections

## Process Steps

### Workflow Summary
1. **Prepare**: Load and review unmapped CSV files
2. **Analyze**: Find potential matches using keterangan clues
3. **Evaluate**: Apply gate system logic to validate matches
4. **Document**: Record corrections in standardized format
5. **Validate**: Cross-reference with official documents

### 1. Preparation
- Ensure both source CSV files exist for the target province
- Review the structure and content of both files
- Note the total number of unmapped records in each file

### 2. Analysis Approach
Find possible matches between Detail → POS records:

**Primary Strategy**: Use `detail_keterangan` column as your guide
- Look for explicit name changes (e.g., "semula Kisam menjadi Kuta Buluh")
- Check for relocations between kecamatan
- Note official decree references
- Identify historical name variations

**Secondary Strategy**: Manual similarity matching
- Compare normalized names between detail and POS files
- Apply gate system logic for fuzzy matches
- Consider geographical context when names are similar

### 3. Matching Criteria
- **Exact matches**: Direct name matches after normalization
- **Fuzzy matches**: Similar names with minor variations following the gate system
- **Contextual matches**: Using geographical proximity or administrative relationships
- **Documentation-based**: Using official references in keterangan column

### 4. Gate System Logic (Follow postal_code_matcher.py)
Manual analysis must follow the same hierarchical gate system used by the automated matcher:

1. **Province Gate**: Similarity ≥ 0.95
   - Province names must match with very high confidence

2. **Kabupaten Gate**: Similarity ≥ 0.95
   - Regency/city names must match with very high confidence

3. **Kecamatan Gate**: Similarity ≥ 0.75
   - Sub-district names must match with good confidence

4. **Kelurahan Gate**: Similarity ≥ 0.70
   - Village names must match with reasonable confidence

5. **Overall Gate**: Weighted score ≥ 0.80
   - Overall = (0.4 × kecamatan_similarity) + (0.6 × kelurahan_similarity)

**Important**: Each gate must pass independently. If any gate fails, the potential match is rejected. This prevents false matches where only one level matches well.

**Manual Similarity Calculation**: Use Jaro-Winkler distance algorithm (same as automated system) when evaluating potential matches.

**Practical Examples:**

*Accepted Match (with fuzzy kecamatan):*
- Province: "Aceh" vs "Aceh" → Similarity = 1.0 ≥ 0.95 ✓
- Kabupaten: "Aceh Tenggara" vs "Aceh Tenggara" → Similarity = 1.0 ≥ 0.95 ✓
- Kecamatan: "Bambel" vs "Bambel District" → Similarity = 0.85 ≥ 0.75 ✓
- Kelurahan: "Kuta Buluh" vs "Kuta Buluh" → Similarity = 1.0 ≥ 0.70 ✓
- Overall: (0.4 × 0.85) + (0.6 × 1.0) = 0.94 ≥ 0.80 ✓
**Result**: Valid match accepted

*Rejected Match (fails kecamatan gate):*
- Province: "Aceh" vs "Aceh" → Similarity = 1.0 ≥ 0.95 ✓
- Kabupaten: "Aceh Tenggara" vs "Aceh Tenggara" → Similarity = 1.0 ≥ 0.95 ✓
- Kecamatan: "Bambel" vs "Sumber Jaya" → Similarity = 0.45 < 0.75 ✗
- **Result**: Match rejected (even if kelurahan matches perfectly)

**Special Case - Kecamatan Relocations:**
If `detail_keterangan` explicitly indicates a kelurahan/desa relocation to another kecamatan, override the kecamatan gate:
- Check if keterangan mentions "pemekaran", "perubahan batas", or specific kecamatan changes
- Find POS records in the *correct* (new) kecamatan mentioned in keterangan
- Apply gates using the relocated kecamatan name
- Document the relocation in References column

### 5. Documentation Format
Create the output file with the following structure:

```markdown
# POS Data Corrections for {Province}

## Overview
This document tracks corrections applied to POS (Pos Indonesia) data for {Province} province, focusing on specific naming inconsistencies identified during data matching processes.

## Corrections Table

| No | Province | Regency/City | Field | Source | Original Value | Corrected Value | References |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | ... | ... | ... | ... | ... | ... | ... |
```

**Column Explanations:**
- **No**: Sequential correction number
- **Province**: Always the target province name
- **Regency/City**: Administrative regency or city where correction applies
- **Field**: Data field being corrected (`desa_kelurahan`, `kecamatan`, etc.)
- **Source**: Always "POS Data" (indicating POS data is being corrected)
- **Original Value**: The incorrect name in POS data
- **Corrected Value**: The correct official name from government sources `src/log/{province}/{province}_remain_unmapped_detail.csv`
- **References**: Official document citations justifying the correction

**Optional: Remaining Unmapped Records Section**
After documenting applied corrections, include a section for records that remain unmapped:

```markdown
## Remaining Unmapped Records

After applying the above corrections, the following records remain unmapped and may require further analysis or data updates.

### Unmapped Detail Records
These official government records could not be matched to POS data:

| No | Province | Regency/City | Kecamatan | Kode Kelurahan | Kelurahan/Desa | Keterangan |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | ... | ... | ... | ... | ... | ... |
```

This section provides complete transparency about analysis coverage and identifies areas needing future attention.

### 6. Validation
- Cross-reference all corrections with official government documents
- Ensure corrections align with official ministerial decree compliance
- Verify geographical and administrative consistency

## Example: Aceh Province

### Source Files
- `src/log/aceh/aceh_remain_unmapped_detail.csv` (26 records)
- `src/log/aceh/aceh_remain_unmapped_pos.csv` (many records)

### Analysis Example
1. **Detail record**: `Kisam` in Bambel kecamatan, Kabupaten Aceh Tenggara
   - Keterangan: "Perubahan nama desa semula Kisam menjadi Kuta Buluh"
2. **POS record**: `Kisam` in Bambel kecamatan
3. **Correction**: Change POS `Kisam` to `Kuta Buluh`

### Key Patterns Identified
- Many corrections involve adding "Meunasah" prefix to village names
- Some villages relocated between kecamatan
- Official name changes documented in government decrees
- Removal of "Kp." (Kampong) prefixes for standardization

### Result
- 26 corrections documented in `src/datas/comparing_pos/aceh.md`
- All corrections backed by official references
- Ready for integration into automated correction systems

## Tools and References

### Required Tools
- CSV viewer/editor (Excel, LibreOffice, or text editor)
- Markdown editor for documentation
- Access to official government documents for validation

### Reference Documents
- Official ministerial decrees (e.g., Keputusan Menteri Dalam Negeri Nomor 300.2.2-2138 Tahun 2025)
- Provincial qanuns and decrees
- Ministry of Home Affairs clarifications
- Historical administrative change records

## Quality Assurance

### Completeness Check
- Review all unmapped detail records
- Ensure no obvious matches were missed
- Document any records that remain unmapped after analysis

### Accuracy Validation
- Verify all corrections against primary sources
- Cross-check geographical locations
- Ensure administrative hierarchy consistency

### Documentation Standards
- Include complete official references
- Use consistent formatting
- Provide clear explanations for each correction

## Next Steps

After completing manual analysis for a province:
1. Update automated correction systems with new mappings
2. Integrate corrections into data processing pipelines
3. Re-run matching processes to reduce unmapped records
4. Document any new patterns discovered for future reference

## Notes

- This is a manual process requiring domain knowledge of Indonesian administrative divisions
- Each province may have unique naming patterns and historical changes
- Official documents should always take precedence over POS data
- Regular updates may be needed as new administrative changes occur