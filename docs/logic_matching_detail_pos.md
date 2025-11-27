# Matching Logic in scoring_hierarchical.py

## Source Path
`src/scripts/scoring_hierarchical.py`

## Overview
This script performs hierarchical blocking-based fuzzy matching to link administrative region data from two sources: detail records and postal (POS) records. It aims to match regions like provinces, districts, sub-districts, and villages efficiently by using blocking techniques to reduce comparison space and fuzzy string matching to handle variations in names.

The script loads data for a specific province, applies matching logic, and saves results with confidence levels and suggested actions for review.

## Step-by-Step Explanation of the Matching Process

1. **Data Loading**:
   - Load detail records from `{province}_detail_join.csv`.
   - Load POS records from `{province}_pos_join.csv`.
   - Both files contain administrative region data with fields like province, district, sub-district, and village names.

2. **Configuration Setup**:
   - Set thresholds for similarity scores (e.g., 0.85 for sub-districts, 0.80 for villages).
   - Choose a string similarity algorithm (e.g., Jaro-Winkler for handling typos).
   - Define high confidence threshold (e.g., 0.90).

3. **Matching Execution**:
   - Use HierarchicalBlockMatcher to perform blocked fuzzy matching.
   - Block on higher-level fields (province and district) to group similar records.
   - Apply fuzzy matching within blocks to find best matches based on similarity scores.

4. **Scoring and Classification**:
   - Calculate similarity scores for sub-district and village names.
   - Assign match levels: exact, high_confidence, medium_confidence, low_confidence, or no_match.
   - Determine match types: auto_accept, manual_review, investigate, or match_all.

5. **Deduplication and Saving**:
   - Ensure unique matches and handle duplicates.
   - Save results to a CSV file with reordered columns for easy review.
   - Print statistics on match counts and rates.

## Key Components

- **Hierarchical Blocking**: Groups records by province and district to limit comparisons, improving efficiency for large datasets.
# Matching Logic in scoring_hierarchical.py

## Source Path
`src/scripts/scoring_hierarchical.py`

## Overview
This script performs hierarchical blocking-based fuzzy matching to link administrative region data from two sources: detail records and postal (POS) records. It aims to match regions like provinces, districts, sub-districts, and villages efficiently by using blocking techniques to reduce comparison space and fuzzy string matching to handle variations in names.

The script loads data for a specific province, applies matching logic, and saves results with confidence levels and suggested actions for review.

## Step-by-Step Explanation of the Matching Process

1. **Data Loading**:
   - Load detail records from `{province}_detail_join.csv`.
   - Load POS records from `{province}_pos_join.csv`.
   - Both files contain administrative region data with fields like province, district, sub-district, and village names.

2. **Configuration Setup**:
   - Set thresholds for similarity scores (e.g., 0.85 for sub-districts, 0.80 for villages).
   - Choose a string similarity algorithm (e.g., Jaro-Winkler for handling typos).
   - Define high confidence threshold (e.g., 0.90).

3. **Matching Execution**:
   - Use HierarchicalBlockMatcher to perform blocked fuzzy matching.
   - Block on higher-level fields (province and district) to group similar records.
   - Apply fuzzy matching within blocks to find best matches based on similarity scores.

4. **Scoring and Classification**:
   - Calculate similarity scores for sub-district and village names.
   - Assign match levels: exact, high_confidence, medium_confidence, low_confidence, or no_match.
   - Determine match types: auto_accept, manual_review, investigate, or match_all.

5. **Deduplication and Saving**:
   - Ensure unique matches and handle duplicates.
   - Save results to a CSV file with reordered columns for easy review.
   - Print statistics on match counts and rates.

## Key Components

- **Hierarchical Blocking**: Groups records by province and district to limit comparisons, improving efficiency for large datasets.
- **Fuzzy Matching**: Uses string similarity algorithms to match names with typos or variations (e.g., "Jakarta" vs. "Jakrta").
- **Scoring**: Assigns numerical confidence scores based on similarity, with thresholds for different levels.
- **Deduplication**: Ensures each detail record matches at most one POS record, preventing duplicate links.

## Answers to Three Specific Questions

### 1. What is hierarchical blocking and how does it improve matching efficiency?
Hierarchical blocking groups records by shared higher-level attributes (like province and district) before comparing lower-level details. This reduces the number of comparisons from potentially millions to thousands, making the process faster and more scalable.

In the code, this is implemented using the recordlinkage library's indexer, which creates blocks on exact matches for 'provinsi' and 'kabupaten_kota' fields. By blocking first on province and then on district within that province, the matcher generates candidate pairs only for records that share these higher-level identifiers. This blocking mechanism ensures that fuzzy matching is performed only within relevant subsets, dramatically reducing computational complexity. For instance, without blocking, comparing all detail records against all POS records could involve cross-products of large datasets, but blocking limits comparisons to records within the same administrative hierarchy level. The output reflects this efficiency: for a province like Aceh, the number of candidate pairs is constrained to those within matching province and district groups, leading to faster processing and higher accuracy by avoiding irrelevant comparisons that could produce false positives.

**Example**: For Aceh province, instead of comparing every village across all provinces, it first blocks by province "Aceh" and district "Banda Aceh", then matches villages within that block.

### 2. How does fuzzy matching handle name variations?
Fuzzy matching calculates similarity scores between strings using algorithms like Jaro-Winkler, which accounts for character swaps, insertions, and deletions. It finds close matches even with typos or abbreviations.

The implementation normalizes both kecamatan and kelurahan names using a custom `normalize_for_matching` function before applying the Jaro-Winkler algorithm, which is particularly effective for Indonesian administrative names that may have spacing, case, or minor spelling variations. The similarity scores are computed for both kecamatan and kelurahan fields, and an overall confidence is derived as a weighted average (40% kecamatan, 60% kelurahan) to prioritize the final administrative level. This approach explains why certain matches achieve high scores despite variations: the algorithm tolerates common errors like missing spaces or transposed characters, producing scores that reflect the degree of similarity. Low scores result when names diverge significantly, indicating potential mismatches that require further review. The blocking mechanism ensures these fuzzy comparisons are only made within relevant groups, enhancing the reliability of the scores by reducing noise from unrelated records.

**Example**: "Kecamatan Setia Budi" might match "Kecamatan Setiabudi" with a high score (e.g., 0.95), while "Kecamatan Ancol" would score low (e.g., 0.30).

### 3. What is deduplication in this context and why is it important?
Deduplication ensures each record from the detail dataset is matched to at most one record from the POS dataset, avoiding multiple links that could cause data inconsistencies. It's important for maintaining data integrity in administrative mappings.

In the code, deduplication is achieved by sorting the candidate pairs by overall_confidence and kelurahan_desa_similarity in descending order, then dropping duplicates based on the detail record index, keeping only the highest-scoring match for each detail record. This one-to-one mapping prevents over-linking, which could lead to inflated match counts or conflicting assignments in downstream data processing. The process filters out low-similarity pairs early (requiring at least 0.7 on one field) and categorizes matches into levels (exact, high_confidence, etc.), ensuring that only the most appropriate POS record is retained per detail record. This mechanism is crucial because administrative data often has near-duplicate entries, and without deduplication, a single detail village could incorrectly link to multiple POS villages, compromising the accuracy of regional mappings and postal code assignments.

**Example**: If a village name appears in multiple POS records, the script selects the best match based on overall confidence and discards others to prevent duplicate assignments.

## Design Flaw in One-to-Many Matching

### Deep Analysis of Question 3: Deduplication and Its Role in Preventing One-to-Many Issues

Building on Question 3, which addresses deduplication, this section delves into the underlying design flaw that deduplication mitigates: the potential for one-to-many matching in the absence of proper safeguards. One-to-many matching occurs when a single POS record is matched to multiple detail records, leading to ambiguous or incorrect linkages. This flaw stems from the fuzzy matching process, which can identify multiple plausible matches for a given POS entry based on similarity scores.

#### Step-by-Step Process Leading to One-to-Many Matching

1. **Initial Candidate Generation**: The hierarchical blocking creates candidate pairs by grouping records that share province and district names. Within these blocks, fuzzy matching compares sub-district (kecamatan) and village (kelurahan) names between detail and POS datasets.

2. **Similarity Scoring**: For each candidate pair, similarity scores are calculated using Jaro-Winkler for both kecamatan and kelurahan fields. An overall confidence score is computed as a weighted average (40% kecamatan, 60% kelurahan). Pairs with at least one field scoring 0.7 or higher are retained as potential matches.

3. **Unconstrained Matching**: Without deduplication, all candidate pairs above the threshold are considered valid matches. This means a single POS record could have multiple detail records with high similarity scores, especially in cases of name variations, duplicates, or closely related administrative units.

4. **Resulting One-to-Many Relationships**: The output would include multiple detail records linked to the same POS record, violating the intended one-to-one mapping and causing data integrity issues.

#### Why POS Matches to Both Details

POS records match to multiple details primarily due to the inherent flexibility of fuzzy matching, which tolerates variations in naming. For instance:
- **Name Variations**: A POS village name like "Desa Sukamaju" might match both "Desa Sukamaju Lama" and "Desa Sukamaju Baru" in the detail dataset if they share high similarity.
- **Administrative Splits or Merges**: Historical changes in administrative boundaries can result in similar names persisting in both datasets.
- **Data Quality Issues**: Typos, abbreviations, or inconsistent formatting in either dataset can lead to multiple high-scoring matches for a single POS entry.
- **Blocking Limitations**: While hierarchical blocking reduces comparisons, it doesn't eliminate all ambiguities within blocks, allowing fuzzy matching to propose multiple candidates.

This occurs because the matching algorithm prioritizes similarity over uniqueness, potentially linking one POS record to several detail records that all exceed the confidence threshold.

#### Implications of One-to-Many Matching

- **Data Inconsistencies**: Multiple detail records pointing to the same POS record can lead to conflicting postal code assignments or administrative mappings.
- **Inflated Match Counts**: Over-counting matches distorts statistics and analytics derived from the data.
- **Downstream Errors**: In applications like address validation or logistics, one-to-many links can cause routing errors or failed deliveries.
- **Review Burden**: Manual review becomes more complex, as reviewers must decide which match to retain, potentially introducing human error.
- **System Performance**: Retaining multiple matches increases data volume and processing overhead in subsequent steps.

#### Potential Fixes

The current implementation addresses this flaw through deduplication, as detailed in Question 3. Additional or alternative fixes include:
- **Stricter Thresholds**: Raising similarity thresholds to reduce the number of candidate pairs, minimizing ambiguities.
- **Additional Blocking Keys**: Incorporating more hierarchical levels (e.g., postal codes) into blocking to further narrow candidate groups.
- **Machine Learning Models**: Using trained models to predict the best match based on multiple features, not just similarity scores.
- **Manual Curation**: Implementing a feedback loop where human reviewers validate and correct matches, refining the algorithm over time.
- **Unique Identifiers**: If available, matching on unique codes (e.g., administrative IDs) instead of names to enforce one-to-one relationships.

### Context and Real-World Implications

Detail data in this project originates from recent government sources, such as official decrees and administrative updates, ensuring it reflects the latest administrative boundaries and naming conventions. In contrast, POS (postal) data may derive from older datasets or third-party sources that lag behind official changes, containing outdated or inconsistent information.

This discrepancy exacerbates the one-to-many matching issue in real-world scenarios. For example, consider a kelurahan (village) that has been reassigned from one kecamatan (sub-district) to another due to administrative reforms. The detail dataset, being current, correctly places the kelurahan under its new kecamatan. However, the POS dataset, if outdated, might still associate the kelurahan with the old kecamatan or list it under both. Fuzzy matching could then link the POS record to multiple detail records—one under the old kecamatan and another under the new—creating a one-to-many relationship that reflects historical inaccuracies rather than current reality.

Such mismatches can have practical consequences, including incorrect postal deliveries, misaligned government services, or errors in demographic reporting. In regions undergoing frequent administrative changes, like expanding urban areas or post-disaster reorganizations, this flaw highlights the need for regular data synchronization and robust matching algorithms to maintain accurate regional mappings.

## Critical Edge Case: Administrative Reorganization (Kelurahan Reassignment)

### Problem Statement

A significant challenge arises when **kelurahan (villages) are administratively reassigned** from one kecamatan (sub-district) to another. Since detail data comes from recent government sources while POS data may be outdated, the matcher can produce **incorrect matches** that appear valid based on name similarity alone.

### Real-World Example

Consider this scenario where a kelurahan has been moved between kecamatans:

**Detail Data (Recent Government Data):**
```
Record 1:
  province: Aceh
  kabupaten_kota: Kabupaten Aceh Barat
  kecamatan: Panton Reu
  kelurahan_desa: Lueng Jawa

Record 2:
  province: Aceh
  kabupaten_kota: Kabupaten Aceh Barat
  kecamatan: Woyla
  kelurahan_desa: Kuala Manyeu
```

**POS Data (Potentially Outdated):**
```
POS Record:
  province: Aceh
  kabupaten_kota: Kabupaten Aceh Barat
  kecamatan: Wouyla
  kelurahan_desa: Lueng Jawa
```

**Historical Context:** The village "Lueng Jawa" was administratively moved from "Wouyla" kecamatan to "Panton Reu" kecamatan. The detail data reflects this change, but the POS data still shows the old assignment.

### Step-by-Step Matching Analysis

#### Step 1: Hierarchical Blocking

The blocker creates candidate pairs based on exact matches for `provinsi` and `kabupaten_kota`:

```python
indexer.block('provinsi')      # Must match: "Aceh"
indexer.block('kabupaten_kota') # Must match: "Kabupaten Aceh Barat"
```

**Candidate Pairs Generated:**
- ✅ Detail Record 1 (Panton Reu / Lueng Jawa) vs POS (Wouyla / Lueng Jawa)
- ✅ Detail Record 2 (Woyla / Kuala Manyeu) vs POS (Wouyla / Lueng Jawa)

**Key Insight:** The blocker does NOT block on kecamatan, which is **intentional and correct** to allow matching across kecamatan boundaries for cases like administrative reassignments.

#### Step 2: Fuzzy String Matching

For each candidate pair, similarity scores are calculated using Jaro-Winkler algorithm:

**Detail Record 1 vs POS:**
```
Kecamatan comparison:
  "Panton Reu" vs "Wouyla"
  → Similarity: ~0.20 (very different names)

Kelurahan comparison:
  "Lueng Jawa" vs "Lueng Jawa"
  → Similarity: 1.00 (exact match)
```

**Detail Record 2 vs POS:**
```
Kecamatan comparison:
  "Woyla" vs "Wouyla"
  → Similarity: ~0.95 (typo/spelling variation)

Kelurahan comparison:
  "Kuala Manyeu" vs "Lueng Jawa"
  → Similarity: ~0.30 (different names)
```

#### Step 3: Filtering Low-Similarity Pairs

The code filters out pairs where both fields have low similarity:

```python
# Line 167-170 in hierarchical_blocker.py
features = features[
    (features['kecamatan_similarity'] >= 0.7) | 
    (features['kelurahan_desa_similarity'] >= 0.7)
]
```

**Results:**
- ✅ **Detail Record 1 vs POS: KEPT** (kelurahan_desa_similarity = 1.0 ≥ 0.7)
- ✅ **Detail Record 2 vs POS: KEPT** (kecamatan_similarity = 0.95 ≥ 0.7)

Both pairs pass the filter because at least one field has high similarity.

#### Step 4: Overall Confidence Calculation

Weighted average is calculated with 40% weight on kecamatan and 60% weight on kelurahan:

```python
overall_confidence = 0.4 * kecamatan_similarity + 0.6 * kelurahan_desa_similarity
```

**Detail Record 1 vs POS:**
```
overall_confidence = 0.4 * 0.20 + 0.6 * 1.00
                   = 0.08 + 0.60
                   = 0.68

Match Level: "low_confidence" (0.60 ≤ 0.68 < 0.75)
Suggested Action: "investigate"
```

**Detail Record 2 vs POS:**
```
overall_confidence = 0.4 * 0.95 + 0.6 * 0.30
                   = 0.38 + 0.18
                   = 0.56

Match Level: "no_match" (< 0.60)
Suggested Action: "reject"
```

#### Step 5: Match Level Categorization

Based on confidence thresholds:

| Match Level | Confidence Range | Suggested Action |
|-------------|------------------|------------------|
| exact | Both fields = 1.0 | auto_accept |
| high_confidence | ≥ 0.90 | auto_accept |
| medium_confidence | 0.75 - 0.89 | manual_review |
| low_confidence | 0.60 - 0.74 | investigate |
| no_match | < 0.60 | reject |

**Detail Record 1 vs POS:**
- Match Level: `low_confidence`
- Suggested Action: `investigate`
- **Status: Flagged for investigation** ✅

**Detail Record 2 vs POS:**
- Match Level: `no_match`
- Suggested Action: `reject`
- **Status: Filtered out** ❌

#### Step 6: Deduplication

The code keeps only the best match for each detail record:

```python
# Sort by confidence and kelurahan similarity (descending)
features = features.sort_values(
    by=['overall_confidence', 'kelurahan_desa_similarity'], 
    ascending=[False, False]
)

# Keep first (best) match per detail record
features = features.drop_duplicates(subset=['level_0'], keep='first')
```

**Final Results:**
- ✅ Detail Record 1 → POS (confidence: 0.68, flagged as "investigate")
- ❌ Detail Record 2 → No match (filtered out as "no_match")

### The Problem Identified

**What Actually Happened:**
- "Lueng Jawa" was moved from "Wouyla" to "Panton Reu" kecamatan
- Detail data shows the **new** assignment (Panton Reu)
- POS data shows the **old** assignment (Wouyla)

**What the Matcher Did:**
- ✅ Correctly identified "Lueng Jawa" in both datasets (exact name match)
- ⚠️ **Detected kecamatan mismatch** (Panton Reu vs Wouyla)
- ⚠️ Assigned low confidence (0.68) due to kecamatan mismatch
- ✅ Flagged as "investigate" (not auto-accepted)

**The Risk:**
While the current logic correctly flags this as "investigate" rather than auto-accepting, the **root cause is unclear** from the output alone. A reviewer might:
- Assume it's a typo in kecamatan name
- Manually accept the match without realizing it's an administrative change
- Miss the opportunity to update POS data

### Why This Pattern is Dangerous

The current weighting (60% kelurahan, 40% kecamatan) prioritizes village name matching, which makes sense for **typo tolerance** but creates risks for **administrative reorganizations**:

1. **High kelurahan similarity masks kecamatan mismatches**
   - Exact kelurahan match (1.0) can compensate for low kecamatan match (0.2)
   - Results in "low_confidence" (0.68) instead of "no_match"

2. **Ambiguous "investigate" action**
   - Doesn't distinguish between typos and administrative changes
   - Requires manual inspection to identify the real issue

3. **Potential for incorrect auto-accepts**
   - If kecamatan similarity were slightly higher (e.g., 0.5 instead of 0.2)
   - Overall confidence could reach 0.80 → "medium_confidence" → "manual_review"
   - Reviewer might accept without realizing the kecamatan changed

### Recommended Solutions

#### Solution 1: Add Flag Columns (Recommended)

Add diagnostic columns to identify specific mismatch patterns **in the same output file**:

**New Columns to Add:**

1. **`kecamatan_mismatch_flag`**: Indicates kelurahan matches but kecamatan doesn't
   ```python
   kecamatan_mismatch_flag = (
       (kelurahan_desa_similarity >= 0.90) & 
       (kecamatan_similarity < 0.70)
   )
   ```
   - `True`: Potential administrative reassignment
   - `False`: Normal matching pattern

2. **`potential_admin_change`**: Suggests administrative reorganization
   ```python
   potential_admin_change = (
       (kelurahan_desa_similarity >= 0.95) &  # Near-exact kelurahan match
       (kecamatan_similarity < 0.50) &   # Significant kecamatan difference
       (provinsi_match == 1) &           # Same province
       (kabupaten_match == 1)            # Same kabupaten
   )
   ```
   - `True`: High likelihood of kelurahan reassignment
   - `False`: Other mismatch type

3. **`pos_duplicate_risk`**: Flags if multiple details match the same POS
   ```python
   # Count how many detail records matched this POS record
   pos_match_count = features.groupby('level_1').size()
   features['pos_duplicate_risk'] = features['level_1'].map(pos_match_count) > 1
   ```
   - `True`: One POS matched to multiple details (one-to-many issue)
   - `False`: One-to-one mapping

4. **`match_quality_flag`**: Overall quality assessment
   ```python
   match_quality_flag = (
       'exact' if match_level == 'exact'
       else 'admin_change_suspected' if potential_admin_change
       else 'duplicate_pos' if pos_duplicate_risk
       else 'kecamatan_mismatch' if kecamatan_mismatch_flag
       else 'normal'
   )
   ```

**Example Output for the Scenario:**

| detail_kelurahan | detail_kecamatan | pos_kelurahan | pos_kecamatan | match_level | overall_confidence | kecamatan_mismatch_flag | potential_admin_change | match_quality_flag |
|------------------|------------------|---------------|---------------|-------------|--------------------|-----------------------|------------------------|-------------------|
| Lueng Jawa | Panton Reu | Lueng Jawa | Wouyla | low_confidence | 0.68 | True | True | admin_change_suspected |

**Benefits:**
- ✅ All data in one file (no separate reports needed)
- ✅ Easy to filter and sort by flag columns
- ✅ Clear indication of issue type for reviewers
- ✅ Enables automated workflows (e.g., flag all `potential_admin_change` for POS data team)

#### Solution 2: Stricter Auto-Accept Criteria

Require **both** kecamatan and kelurahan to have high similarity for auto-accept:

```python
def categorize_match(row):
    if row['provinsi_match'] == 1 and row['kabupaten_match'] == 1:
        # Exact: Both fields must be perfect
        if row['kecamatan_similarity'] == 1.0 and row['kelurahan_desa_similarity'] == 1.0:
            return 'exact'
        
        # High confidence: BOTH must be high (prevents admin change auto-accepts)
        elif (row['kecamatan_similarity'] >= 0.85 and 
              row['kelurahan_desa_similarity'] >= 0.85 and
              row['overall_confidence'] >= 0.90):
            return 'high_confidence'
        
        # Medium: Good overall but one field lower
        elif row['overall_confidence'] >= 0.75:
            return 'medium_confidence'
        
        # Low: Significant mismatch
        elif row['overall_confidence'] >= 0.60:
            return 'low_confidence'
    
    return 'no_match'
```

**Impact:**
- Prevents cases where high kelurahan similarity compensates for low kecamatan similarity
- Reduces auto-accept rate but increases accuracy
- Administrative changes would never be auto-accepted

#### Solution 3: Bidirectional Deduplication

Ensure one-to-one mapping by deduplicating on both detail and POS indices:

```python
# Current: Only deduplicates on detail records
features = features.drop_duplicates(subset=['level_0'], keep='first')

# Add: Also deduplicate on POS records
features = features.sort_values(
    by=['overall_confidence', 'kelurahan_desa_similarity'], 
    ascending=[False, False]
)
features = features.drop_duplicates(subset=['level_1'], keep='first')
```

**Impact:**
- Prevents one POS record from matching multiple detail records
- Ensures strict one-to-one mapping
- May discard valid matches if POS data is incomplete

### Recommended Implementation: Combined Approach

Implement **Solution 1 (Flag Columns) + Solution 2 (Stricter Criteria)**:

1. **Add all diagnostic flag columns** to provide visibility
2. **Require both fields high** for auto-accept to prevent incorrect matches
3. **Keep current deduplication** (detail-side only) to preserve all potential matches
4. **Use flags for workflow routing**:
   - `exact` + `match_quality_flag='exact'` → Auto-accept
| high_confidence | ≥ 0.90 | auto_accept |
| medium_confidence | 0.75 - 0.89 | manual_review |
| low_confidence | 0.60 - 0.74 | investigate |
| no_match | < 0.60 | reject |

**Detail Record 1 vs POS:**
- Match Level: `low_confidence`
- Suggested Action: `investigate`
- **Status: Flagged for investigation** ✅

**Detail Record 2 vs POS:**
- Match Level: `no_match`
- Suggested Action: `reject`
- **Status: Filtered out** ❌

#### Step 6: Deduplication

The code keeps only the best match for each detail record:

```python
# Sort by confidence and kelurahan similarity (descending)
features = features.sort_values(
    by=['overall_confidence', 'kelurahan_desa_similarity'], 
    ascending=[False, False]
)

# Keep first (best) match per detail record
features = features.drop_duplicates(subset=['level_0'], keep='first')
```

**Final Results:**
- ✅ Detail Record 1 → POS (confidence: 0.68, flagged as "investigate")
- ❌ Detail Record 2 → No match (filtered out as "no_match")

### The Problem Identified

**What Actually Happened:**
- "Lueng Jawa" was moved from "Wouyla" to "Panton Reu" kecamatan
- Detail data shows the **new** assignment (Panton Reu)
- POS data shows the **old** assignment (Wouyla)

**What the Matcher Did:**
- ✅ Correctly identified "Lueng Jawa" in both datasets (exact name match)
- ⚠️ **Detected kecamatan mismatch** (Panton Reu vs Wouyla)
- ⚠️ Assigned low confidence (0.68) due to kecamatan mismatch
- ✅ Flagged as "investigate" (not auto-accepted)

**The Risk:**
While the current logic correctly flags this as "investigate" rather than auto-accepting, the **root cause is unclear** from the output alone. A reviewer might:
- Assume it's a typo in kecamatan name
- Manually accept the match without realizing it's an administrative change
- Miss the opportunity to update POS data

### Why This Pattern is Dangerous

The current weighting (60% kelurahan, 40% kecamatan) prioritizes village name matching, which makes sense for **typo tolerance** but creates risks for **administrative reorganizations**:

1. **High kelurahan similarity masks kecamatan mismatches**
   - Exact kelurahan match (1.0) can compensate for low kecamatan match (0.2)
   - Results in "low_confidence" (0.68) instead of "no_match"

2. **Ambiguous "investigate" action**
   - Doesn't distinguish between typos and administrative changes
   - Requires manual inspection to identify the real issue

3. **Potential for incorrect auto-accepts**
   - If kecamatan similarity were slightly higher (e.g., 0.5 instead of 0.2)
   - Overall confidence could reach 0.80 → "medium_confidence" → "manual_review"
   - Reviewer might accept without realizing the kecamatan changed

### Recommended Solutions

#### Solution 1: Add Flag Columns (Recommended)

Add diagnostic columns to identify specific mismatch patterns **in the same output file**:

**New Columns to Add:**

1. **`kecamatan_mismatch_flag`**: Indicates kelurahan matches but kecamatan doesn't
   ```python
   kecamatan_mismatch_flag = (
       (kelurahan_desa_similarity >= 0.90) & 
       (kecamatan_similarity < 0.70)
   )
   ```
   - `True`: Potential administrative reassignment
   - `False`: Normal matching pattern

2. **`potential_admin_change`**: Suggests administrative reorganization
   ```python
   potential_admin_change = (
       (kelurahan_desa_similarity >= 0.95) &  # Near-exact kelurahan match
       (kecamatan_similarity < 0.50) &   # Significant kecamatan difference
       (provinsi_match == 1) &           # Same province
       (kabupaten_match == 1)            # Same kabupaten
   )
   ```
   - `True`: High likelihood of kelurahan reassignment
   - `False`: Other mismatch type

3. **`pos_duplicate_risk`**: Flags if multiple details match the same POS
   ```python
   # Count how many detail records matched this POS record
   pos_match_count = features.groupby('level_1').size()
   features['pos_duplicate_risk'] = features['level_1'].map(pos_match_count) > 1
   ```
   - `True`: One POS matched to multiple details (one-to-many issue)
   - `False`: One-to-one mapping

4. **`match_quality_flag`**: Overall quality assessment
   ```python
   match_quality_flag = (
       'exact' if match_level == 'exact'
       else 'admin_change_suspected' if potential_admin_change
       else 'duplicate_pos' if pos_duplicate_risk
       else 'kecamatan_mismatch' if kecamatan_mismatch_flag
       else 'normal'
   )
   ```

**Example Output for the Scenario:**

| detail_kelurahan | detail_kecamatan | pos_kelurahan | pos_kecamatan | match_level | overall_confidence | kecamatan_mismatch_flag | potential_admin_change | match_quality_flag |
|------------------|------------------|---------------|---------------|-------------|--------------------|-----------------------|------------------------|-------------------|
| Lueng Jawa | Panton Reu | Lueng Jawa | Wouyla | low_confidence | 0.68 | True | True | admin_change_suspected |

**Benefits:**
- ✅ All data in one file (no separate reports needed)
- ✅ Easy to filter and sort by flag columns
- ✅ Clear indication of issue type for reviewers
- ✅ Enables automated workflows (e.g., flag all `potential_admin_change` for POS data team)

#### Solution 2: Stricter Auto-Accept Criteria

Require **both** kecamatan and kelurahan to have high similarity for auto-accept:

```python
def categorize_match(row):
    if row['provinsi_match'] == 1 and row['kabupaten_match'] == 1:
        # Exact: Both fields must be perfect
        if row['kecamatan_similarity'] == 1.0 and row['kelurahan_desa_similarity'] == 1.0:
            return 'exact'
        
        # High confidence: BOTH must be high (prevents admin change auto-accepts)
        elif (row['kecamatan_similarity'] >= 0.85 and 
              row['kelurahan_desa_similarity'] >= 0.85 and
              row['overall_confidence'] >= 0.90):
            return 'high_confidence'
        
        # Medium: Good overall but one field lower
        elif row['overall_confidence'] >= 0.75:
            return 'medium_confidence'
        
        # Low: Significant mismatch
        elif row['overall_confidence'] >= 0.60:
            return 'low_confidence'
    
    return 'no_match'
```

**Impact:**
- Prevents cases where high kelurahan similarity compensates for low kecamatan similarity
- Reduces auto-accept rate but increases accuracy
- Administrative changes would never be auto-accepted

#### Solution 3: Bidirectional Deduplication

Ensure one-to-one mapping by deduplicating on both detail and POS indices:

```python
# Current: Only deduplicates on detail records
features = features.drop_duplicates(subset=['level_0'], keep='first')

# Add: Also deduplicate on POS records
features = features.sort_values(
    by=['overall_confidence', 'kelurahan_desa_similarity'], 
    ascending=[False, False]
)
features = features.drop_duplicates(subset=['level_1'], keep='first')
```

**Impact:**
- Prevents one POS record from matching multiple detail records
- Ensures strict one-to-one mapping
- May discard valid matches if POS data is incomplete

### Recommended Implementation: Combined Approach

Implement **Solution 1 (Flag Columns) + Solution 2 (Stricter Criteria)**:

1. **Add all diagnostic flag columns** to provide visibility
2. **Require both fields high** for auto-accept to prevent incorrect matches
3. **Keep current deduplication** (detail-side only) to preserve all potential matches
4. **Use flags for workflow routing**:
   - `exact` + `match_quality_flag='exact'` → Auto-accept
   - `high_confidence` + `match_quality_flag='normal'` → Auto-accept
   - `potential_admin_change=True` → Route to POS data update team
   - `pos_duplicate_risk=True` → Route to data quality team
   - `kecamatan_mismatch_flag=True` → Manual review with context

This approach:
- ✅ Keeps all data in one file
- ✅ Provides clear diagnostic information
- ✅ Prevents incorrect auto-accepts
- ✅ Enables targeted manual review
- ✅ Identifies data quality issues for upstream correction

---

## Proposed Logic: TRUE Cascading Hierarchical Matching

### Overview

The proposed logic implements **strict hierarchical filtering** where each administrative level must independently meet its threshold before proceeding to the next level. This approach eliminates false matches early, especially critical for preventing wrong postal code assignments when villages have been administratively reassigned between kecamatan.

### Design Philosophy

**Key Principle:** Wrong kecamatan = Wrong postal zone = Wrong postal code

Since postal codes follow administrative boundaries, a mismatch at the kecamatan level (even with perfect kelurahan match) indicates:
- Administrative reorganization (village moved to different kecamatan)
- Outdated POS data
- Different postal zones → **Should NOT match**

Unlike weighted averaging approaches that allow high kelurahan scores to compensate for low kecamatan scores, this logic treats each level as a **hard gate** that must be passed independently.

### Step-by-Step Logic

```
Step 1: Fuzzy Match on Provinsi
   - Compute fuzzy similarity for all detail-POS pairs
   - Filter: Keep only pairs where provinsi_similarity >= 0.95
   - Rationale: Province names should be highly standardized
   
Step 2: Fuzzy Match on Kabupaten/Kota
   - For remaining pairs, compute kabupaten similarity
   - Filter: Keep only pairs where kabupaten_similarity >= 0.95
   - Rationale: District names should be highly standardized
   
Step 3: Fuzzy Match on Kecamatan (CRITICAL GATE)
   - For remaining pairs, compute kecamatan similarity
   - Filter: Keep only pairs where kecamatan_similarity >= 0.75
   - Rationale: Sub-district determines postal zone
   - Hard rejection: < 0.75 means different postal zones
   
Step 4: Fuzzy Match on Kelurahan/Desa
   - For remaining pairs, compute kelurahan similarity
   - Filter: Keep only pairs where kelurahan_similarity >= 0.70
   - Rationale: Village names have most variations (prefixes, OCR errors)
   
Step 5: Overall Confidence Check (Combined Safety)
   - Calculate: overall_confidence = 0.4 × kecamatan + 0.6 × kelurahan
   - Filter: Keep only pairs where overall_confidence >= 0.80
   - Rationale: Prevents borderline cases where both barely pass
   
Step 6: Deduplication (1-to-1 Matching)
   - Sort pairs by overall_confidence (descending)
   - Keep best match per detail record
   - Keep best match per POS record
   - Rationale: Minimizes manual review, enforces one-to-one mapping
```

### Comparison with Current Implementation

| Aspect | Current Implementation | Proposed TRUE Cascading |
|--------|----------------------|------------------------|
| **Province/Kabupaten** | Exact blocking (no fuzzy) | Fuzzy matching (0.95 threshold) |
| **Matching Strategy** | Compute all similarities, then weighted average | Progressive filtering with hard gates |
| **Kecamatan Threshold** | Soft (0.85 for high confidence, 0.70 for rejection) | Hard gate (0.75 minimum required) |
| **Kelurahan Threshold** | Soft (0.85 for high confidence) | Hard gate (0.70 minimum required) |
| **Compensation** | ✅ High kelurahan can offset low kecamatan | ❌ No compensation - all levels must pass |
| **Match Categorization** | Exact, High, Medium, Low confidence | Pass/Fail (simpler) |
| **Manual Review** | Many "medium" and "low" confidence cases | Minimal (strict filtering) |
| **POS Deduplication** | Allows 1-to-many (one POS → multiple details) | Strict 1-to-1 (one POS → one detail max) |
| **Computational** | Computes all similarities upfront | Early termination (stops at failed gate) |

### Recommended Thresholds

Based on empirical validation with real Aceh province data:

```python
PROVINCE_THRESHOLD = 0.95      # Very strict (should be standardized)
KABUPATEN_THRESHOLD = 0.95     # Very strict (should be standardized)
KECAMATAN_THRESHOLD = 0.75     # Moderate (allows spacing/abbreviation)
KELURAHAN_THRESHOLD = 0.70     # Lenient (most name variations)
OVERALL_THRESHOLD = 0.80       # Combined safety check
```

**Rationale for Thresholds:**

1. **Province/Kabupaten (0.95):** These levels are highly standardized in both datasets. Very high threshold catches only genuine typos while preventing false matches between similar names (e.g., "Aceh Barat" vs "Aceh Besar").

2. **Kecamatan (0.75):** Moderate threshold accounts for:
   - Spacing variations ("Indra Jaya" vs "Indrajaya")
   - Common abbreviations
   - Minor spelling differences
   - Still strict enough to reject different sub-districts

3. **Kelurahan (0.70):** Most lenient because:
   - Highest variability in naming conventions
   - Geographic prefixes ("Alue Jojo" vs "Jojo")
   - OCR errors from PDF extraction
   - Administrative type variations ("Desa" vs "Kelurahan")

4. **Overall (0.80):** Prevents cases where both kecamatan and kelurahan barely pass individual thresholds but combined confidence is too low.

### Real-World Examples from Data Validation

#### Example 1: Valid Match with Name Variation

```
Detail:  Kabupaten Pidie → Indrajaya → Peutoe
POS:     Kabupaten Pidie → Indra Jaya → Putoe Gapui

Similarities:
- Province: 1.0 (exact)
- Kabupaten: 1.0 (exact)  
- Kecamatan: 0.98 (spacing variation)
- Kelurahan: 0.76 (name variation + descriptor)
- Overall: 0.848

Current Implementation: medium_confidence → manual_review
Proposed Logic: 
  ✅ Pass 0.95 province
  ✅ Pass 0.95 kabupaten
  ✅ Pass 0.75 kecamatan (0.98)
  ✅ Pass 0.70 kelurahan (0.76)
  ✅ Pass 0.80 overall (0.848)
  → MATCH ✅
```

#### Example 2: Geographic Prefix Issue

```
Detail:  Kabupaten Pidie → Mutiara Timur → Jojo
POS:     Kabupaten Pidie → Mutiara Timur → Alue Jojo

Similarities:
- Province: 1.0 (exact)
- Kabupaten: 1.0 (exact)
- Kecamatan: 1.0 (exact - perfect match!)
- Kelurahan: 0.583 ("Jojo" vs "Alue Jojo" - missing prefix)
- Overall: 0.75

Analysis:
- "Alue" = river/stream in Acehnese
- Likely the same place with geographic descriptor
- Kecamatan perfect match (1.0) strongly suggests validity

Current Implementation: medium_confidence → manual_review
Proposed Logic:
  ✅ Pass 0.95 province
  ✅ Pass 0.95 kabupaten
  ✅ Pass 0.75 kecamatan (1.0)
  ❌ FAIL 0.70 kelurahan (0.583)
  → NO MATCH ❌

Issue: This reveals a normalization gap - geographic prefixes should be handled.
```

#### Example 3: Administrative Reassignment (Should Reject)

```
Detail:  Aceh Barat → Panton Reu → Lueng Jawa
POS:     Aceh Barat → Wouyla → Lueng Jawa

Similarities:
- Province: 1.0 (exact)
- Kabupaten: 1.0 (exact)
- Kecamatan: 0.20 (completely different)
- Kelurahan: 1.0 (exact - but in different kecamatan!)
- Overall: 0.68

Historical Context: Village "Lueng Jawa" was moved from Wouyla to Panton Reu

Current Implementation: low_confidence → investigate (creates match)
Proposed Logic:
  ✅ Pass 0.95 province
  ✅ Pass 0.95 kabupaten
  ❌ FAIL 0.75 kecamatan (0.20)
  → NO MATCH ✅ (Correct! Wrong postal zone)
```

### Advantages of Proposed Logic

1. **✅ Eliminates Wrong Postal Code Assignments**
   - Kecamatan mismatch → automatic rejection
   - No risk of assigning outdated postal codes
   - Prevents administrative reorganization confusion

2. **✅ Minimizes Manual Review**
   - Strict gates eliminate borderline cases
   - Pass/fail decisions instead of confidence categories
   - Fewer "medium" and "low" confidence matches to review

3. **✅ Faster Processing**
   - Early termination when gate fails
   - No need to compute all similarities if early level fails
   - More efficient for large datasets

4. **✅ Simpler Logic**
   - No weighted averaging complexity
   - Clear threshold-based decisions
   - Easier to debug and tune

5. **✅ Enforces Data Quality**
   - Unmatched records highlight POS data issues
   - Forces attention to normalization gaps
   - Identifies outdated POS records

### Known Issues and Considerations

#### Issue 1: Lower Match Rate

**Problem:** Stricter thresholds result in fewer overall matches compared to weighted averaging.

**Impact:**
- More detail records remain unmatched
- Valid matches with borderline similarities rejected
- Requires high-quality normalization

**Mitigation:**
- Improve `normalize_for_matching` to handle variations
- Empirically tune thresholds based on real data
- Accept that "no match" is better than "wrong match" for postal codes

#### Issue 2: Normalization Dependency

**Problem:** Geographic prefixes and local language variations cause valid matches to fail.

**Examples:**
- "Alue" (river), "Gampong" (village), "Kampung" (village) in Acehnese
- "Desa" vs "Kelurahan" administrative types
- OCR errors from PDF extraction

**Mitigation:**
- Enhance normalization to strip common prefixes
- Region-specific normalization rules
- Token-based matching as fallback

**Recommended Enhancement:**
```python
ACEHNESE_PREFIXES = ['alue', 'gampong', 'kampung', 'blang', 'meunasah']
ADMIN_PREFIXES = ['desa', 'kelurahan', 'kecamatan']

def normalize_for_matching(text, field_type, region=''):
    text = text.lower().strip()
    
    # Remove administrative type prefixes
    text = remove_prefix(text, ADMIN_PREFIXES)
    
    # Remove region-specific geographic prefixes
    if region == 'aceh' and field_type == 'kelurahan':
        text = remove_prefix(text, ACEHNESE_PREFIXES)
    
    return text
```

#### Issue 3: Ambiguous Cases with Token Overlap

**Problem:** When multiple detail records have tokens that appear in a single POS record.

**Example:**
```
POS: "Alue Jojo"

Detail A: "Alue" → similarity with POS = 0.67
Detail B: "Jojo" → similarity with POS = 0.58

Both contain tokens from POS name, but which should match?
```

**Current Behavior:**
- 1-to-1 deduplication picks highest confidence
- "Alue" (0.67) wins, "Jojo" (0.58) remains unmatched

**Considerations:**
- Is "Alue Jojo" a merged village? (both should match historically)
- Is "Alue" just a prefix? (only "Jojo" should match)
- Are they separate villages? (neither should match if incomplete POS data)

**Recommended Approach:**
- Accept that 1-to-1 logic picks best match
- Unmatched records flag potential data issues
- Manual review for ambiguous cases

#### Issue 4: 1-to-1 May Reject Valid Postal Code Sharing

**Problem:** In reality, multiple villages can share the same postal code.

**Example:**
```
POS Record: Postal code 23617 serves Kecamatan Woyla

Detail A (Lueng Jawa): confidence 0.92 → MATCHED
Detail B (Kuala Manyeu): confidence 0.91 → REJECTED (duplicate POS)
Detail C (Teunom): confidence 0.90 → REJECTED (duplicate POS)

Reality: All three might legitimately share postal code 23617
```

**Trade-off:**
- **Current (1-to-many):** Higher match rate, but requires manual review of duplicates
- **Proposed (1-to-1):** Lower match rate, but eliminates duplicate review

**Decision Rationale:**
User prioritizes **minimizing manual review** over maximizing match rate, accepting that some valid postal codes won't be assigned rather than creating ambiguous matches requiring review.

#### Issue 5: No Diagnostic Information for Rejections

**Problem:** When a record doesn't match, it's unclear which gate failed.

**Impact:**
- Hard to identify systematic normalization issues
- Can't distinguish between "close but not quite" and "completely different"
- Difficult to tune thresholds empirically

**Recommended Addition:**
```python
# Save rejection reasons for analysis
output_columns = [
    'detail_kode_kelurahan',
    'rejection_reason',  # NEW: 'province_fail', 'kabupaten_fail', etc.
    'provinsi_similarity',
    'kabupaten_similarity',
    'kecamatan_similarity',
    'kelurahan_similarity'
]
```

This allows post-processing analysis to identify:
- How many fail at each gate
- Distribution of similarities at failure point
- Opportunities for threshold tuning

### Implementation Considerations

#### Fuzzy Matching Algorithm

Use **Jaro-Winkler** algorithm (current implementation):
- Best for typos and character transpositions
- Prioritizes prefix matches (common in Indonesian names)
- Well-suited for administrative names

#### Processing Order

Process hierarchically for efficiency:
```python
# Pseudo-code

pairs = iterate_all_detail_pos_combinations()

# Gate 1
pairs = [(d, p, sim) for d, p in pairs 
         if (sim := fuzzy(d.province, p.province)) >= 0.95]

# Gate 2  
pairs = [(d, p, sim1, sim2) for d, p, sim1 in pairs
         if (sim2 := fuzzy(d.kabupaten, p.kabupaten)) >= 0.95]

# Gate 3 (critical)
pairs = [(d, p, *sims, sim3) for d, p, *sims in pairs
         if (sim3 := fuzzy(d.kecamatan, p.kecamatan)) >= 0.75]

# Gate 4
pairs = [(d, p, *sims, sim4) for d, p, *sims in pairs
         if (sim4 := fuzzy(d.kelurahan, p.kelurahan)) >= 0.70]

# Gate 5 (combined)
pairs = [(*pair, conf) for *pair in pairs
         if (conf := 0.4*pair[5] + 0.6*pair[6]) >= 0.80]

# Deduplicate 1-to-1
pairs = deduplicate_both_sides(pairs, key='overall_confidence')
```

#### Performance Optimization

With 38 provinces, ~500 kabupaten, performance should be acceptable even without early termination. However, for very large datasets:

1. **Block on exact province first** (if no typos expected)
2. **Block on exact kabupaten** within province
3. **Only fuzzy match** on kecamatan and kelurahan

This reduces from O(N×M) to O(N/38 × M/500) comparisons per province.

### Validation Workflow

Before full implementation, validate with sample data:

1. **Extract test set:** 100-200 records from multiple provinces
2. **Manual gold standard:** Human expert labels correct matches
3. **Tune thresholds:** Adjust to maximize precision/recall balance
4. **Analyze failures:** Identify normalization gaps
5. **Iterate:** Improve normalization, re-test
6. **Full deployment:** Once validation metrics acceptable

### Success Metrics

Track these metrics to evaluate logic effectiveness:

- **Match Rate:** % of detail records matched to POS
- **Precision:** % of matches that are correct (needs manual validation)
- **Manual Review Rate:** % requiring human review (target: <5%)
- **Gate Failure Distribution:** Where do most rejections occur?
- **Postal Code Coverage:** % of villages with assigned postal codes

**Target Goals:**
- Match rate: 70-80% (strict but accurate)
- Precision: >95% (very few false matches)
- Manual review: <5% (minimal human effort)

## Real-World Validation Findings (Case Study: Aceh)

Running the TRUE cascading logic on the Aceh dataset provided critical insights that validate the strict hierarchical approach. The separation of unmatched POS records into a "remain" file revealed significant data quality issues in the source POS data that would have caused incorrect matches under the previous logic.

### 1. Prevention of "Same Name, Different Location" Errors
**Scenario:** The village name "Jurong" exists in multiple sub-districts (Kecamatan).

*   **Detail Record:** `Kabupaten Pidie` → `Indrajaya` → `Jurong`
*   **POS Candidate 1:** `Kabupaten Pidie` → `Indra Jaya` → `Jurong` (Postal Code: 24171)
*   **POS Candidate 2:** `Kabupaten Pidie` → `Simpang Tiga` → `Jurong` (Postal Code: 24181)

**Outcome:**
*   **TRUE Cascading:**
    *   Matches Candidate 1 (Kecamatan similarity > 0.75).
    *   **Rejects Candidate 2** immediately at the Kecamatan Gate (Similarity ~0.40 < 0.75).
    *   **Result:** Correct postal code 24171 assigned.
*   **Previous Logic (Weighted Average):**
    *   Candidate 2 would have a high Kelurahan score (1.0) compensating for the low Kecamatan score.
    *   Could result in a "Medium Confidence" match or ambiguous duplicate, potentially assigning the wrong postal code (24181).

### 2. Detection of Cross-Kabupaten Data Issues
**Scenario:** The sub-district "Ulim" appears in two different regencies (Kabupaten) in the POS data, likely due to administrative splitting (pemekaran) or data duplication.

*   **POS Record A:** `Kabupaten Pidie` → `Ulim` → `Meunasah Pupu`
*   **POS Record B:** `Kabupaten Pidie Jaya` → `Ulim` → `Sambungan Baro`

**Outcome:**
*   **TRUE Cascading:** The **Kabupaten Gate** (Threshold 0.95) strictly prevents cross-matching.
    *   If processing `Kabupaten Pidie`, Record B is rejected immediately.
    *   If processing `Kabupaten Pidie Jaya`, Record A is rejected immediately.
*   **Significance:** This isolates data quality issues. The presence of "Ulim" in `Kabupaten Pidie` in the POS data (when it might now belong to `Pidie Jaya`) is flagged as an unmatched record in the "remain" file, prompting a data cleanup rather than silently creating a wrong match.

### 3. The "Remain" File as a Data Quality Report
The `_cascading_matches_remain.csv` output is not just waste; it is a **diagnostic report**. It contains:
1.  **Legitimate Unmatched Zones:** Postal codes for areas not present in the detail dataset.
2.  **Administrative Ghosts:** Old administrative hierarchies (e.g., pre-pemekaran kabupaten) that need to be updated in the POS master data.
3.  **Duplicates:** Redundant entries that confuse standard matching algorithms.

**Conclusion from Validation:**
The strict 1-to-1 cascading logic successfully acts as a **firewall**, allowing only high-quality, structurally sound matches to pass through while quarantining ambiguous or erroneous POS data for manual review or cleanup.

### Conclusion

The proposed TRUE cascading hierarchical logic prioritizes **accuracy over match rate**, recognizing that:
- Wrong postal codes are worse than missing postal codes
- Manual review burden should be minimized
- Administrative boundaries determine postal zones
- Kecamatan mismatch is a hard stop, not a soft penalty

This approach is best suited for scenarios where:
- ✅ Data quality is high enough to support strict thresholds
- ✅ Minimizing manual review is top priority
- ✅ False positives are more costly than false negatives
- ✅ Postal code accuracy is critical for end-user applications