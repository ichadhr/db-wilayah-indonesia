"""
Postal Code Matching Utilities

This module provides functions for matching detail and POS records using both
exact normalized string matching and cascading fuzzy hierarchical matching.

Combines logic from join_parquet_files.py (exact matching) and 
scoring_cascading_polars.py (fuzzy matching) into reusable utility functions.
"""

from abc import ABC, abstractmethod
import polars as pl
import polars_ds as pds
from pathlib import Path
from typing import Tuple, List
from polars.type_aliases import ConcatMethod

from utils.text_utils import normalize_kecamatan, normalize_kelurahan_desa, normalize_for_matching


# Fuzzy matching thresholds (from scoring_cascading_polars.py)
PROVINCE_THRESHOLD = 0.95
KABUPATEN_THRESHOLD = 0.95
KECAMATAN_THRESHOLD = 0.75
KELURAHAN_THRESHOLD = 0.70
OVERALL_THRESHOLD = 0.80

# Similarity weights for overall confidence calculation
KECAMATAN_WEIGHT = 0.4
KELURAHAN_WEIGHT = 0.6


# ============================================================================
# EXACT MATCHING FUNCTIONS (from join_parquet_files.py)
# ============================================================================

def normalize_detail_data(df: pl.DataFrame, province: str) -> pl.DataFrame:
    """
    Prepare detail dataframe by filtering and normalizing.
    
    Args:
        df: Raw detail dataframe
        province: Province name
        
    Returns:
        Prepared detail dataframe with normalized columns
    """
    # Filter for complete records
    df_filtered = df.filter(
        (pl.col('kode_kelurahan').is_not_null()) &
        (pl.col('kode_kelurahan') != '')
    )
    
    # Add normalized columns
    df_filtered = df_filtered.with_columns([
        pl.col('kelurahan').map_elements(
            lambda x: normalize_kelurahan_desa(x) if x else "",
            return_dtype=pl.Utf8
        ).str.to_lowercase().alias('kelurahan_normalized'),
        pl.col('desa').map_elements(
            lambda x: normalize_kelurahan_desa(x) if x else "",
            return_dtype=pl.Utf8
        ).str.to_lowercase().alias('desa_normalized'),
        pl.col('kecamatan').map_elements(
            lambda x: normalize_kecamatan(x) if x else "",
            return_dtype=pl.Utf8
        ).str.to_lowercase().alias('kecamatan_normalized')
    ])
    
    # Combine kelurahan and desa
    df_filtered = df_filtered.with_columns(
        (pl.col('kelurahan_normalized') + pl.col('desa_normalized')).alias('kelurahan_desa_combined')
    )
    
    # Filter for complete hierarchy
    df_complete = df_filtered.filter(
        (pl.col('kecamatan_normalized') != '') &
        (pl.col('kelurahan_desa_combined') != '')
    )
    
    # Add province column
    df_complete = df_complete.with_columns(
        pl.lit(province).alias('provinsi')
    )
    
    return df_complete


def normalize_pos_data(df: pl.DataFrame, province: str) -> pl.DataFrame:
    """
    Prepare POS dataframe by normalizing columns.
    
    Args:
        df: Raw POS dataframe
        province: Province name
        
    Returns:
        Prepared POS dataframe with normalized columns
    """
    # Rename 'province' to 'provinsi' if it exists
    if 'province' in df.collect_schema().names():
        df = df.rename({'province': 'provinsi'})
    
    # Add normalized columns
    df_prepared = df.with_columns([
        pl.col('kecamatan').map_elements(
            lambda x: normalize_kecamatan(x) if x else "",
            return_dtype=pl.Utf8
        ).str.to_lowercase().alias('kecamatan_normalized'),
        pl.col('desa_kelurahan').map_elements(
            lambda x: normalize_kelurahan_desa(x) if x else "",
            return_dtype=pl.Utf8
        ).str.to_lowercase().alias('desa_kelurahan_normalized')
    ])
    
    # Add province column
    df_prepared = df_prepared.with_columns(
        pl.lit(province).alias('provinsi')
    )
    
    return df_prepared


def perform_exact_join(
    detail_df: pl.DataFrame,
    pos_df: pl.DataFrame
) -> Tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    """
    Perform exact left join between normalized detail and POS dataframes.
    
    Args:
        detail_df: Normalized detail dataframe
        pos_df: Normalized POS dataframe
        
    Returns:
        Tuple of (matched_df, unmatched_detail_df, unmapped_pos_df)
    """
    # Perform left join
    df_joined = detail_df.join(
        pos_df.select([
            'kabupaten_kota_source', 'kecamatan_normalized', 
            'desa_kelurahan_normalized', 'provinsi', 'kodepos'
        ]),
        left_on=['kabupaten_kota', 'kecamatan_normalized', 'kelurahan_desa_combined', 'provinsi'],
        right_on=['kabupaten_kota_source', 'kecamatan_normalized', 'desa_kelurahan_normalized', 'provinsi'],
        how='left'
    )
    
    # Add overall_confidence = 1.0 for exact matches
    df_joined = df_joined.with_columns(
        pl.when(pl.col('kodepos').is_not_null())
          .then(pl.lit(1.0))
          .otherwise(pl.lit(None))
          .alias('overall_confidence')
    )
    
    # Split into matched and unmatched
    matched = df_joined.filter(pl.col('kodepos').is_not_null())
    unmatched_detail = df_joined.filter(pl.col('kodepos').is_null())
    
    # Find unmapped POS records (anti-join)
    unmapped_pos = pos_df.join(
        detail_df.select([
            'kabupaten_kota', 'kecamatan_normalized', 
            'kelurahan_desa_combined', 'provinsi'
        ]),
        left_on=['kabupaten_kota_source', 'kecamatan_normalized', 'desa_kelurahan_normalized', 'provinsi'],
        right_on=['kabupaten_kota', 'kecamatan_normalized', 'kelurahan_desa_combined', 'provinsi'],
        how='anti'
    )
    
    # Drop helper columns from matched
    matched = matched.drop([
        'kecamatan_normalized', 'kelurahan_normalized', 
        'desa_normalized', 'kelurahan_desa_combined'
    ])
    
    return matched, unmatched_detail, unmapped_pos


# ============================================================================
# FUZZY MATCHING FUNCTIONS (from scoring_cascading_polars.py)
# ============================================================================

def prepare_for_fuzzy_matching(df: pl.DataFrame, prefix: str) -> pl.DataFrame:
    """
    Add normalized columns for fuzzy similarity calculation.
    
    IMPORTANT: Uses pre-normalized columns (from exact matching phase) as inputs.
    This matches the behavior of scoring_cascading_polars.py which reads from CSV
    files that contain pre-normalized kelurahan_desa values.
    
    Args:
        df: Input dataframe (detail or pos)
        prefix: Prefix for columns ('detail' or 'pos')
        
    Returns:
        DataFrame with normalized fuzzy-matching columns and row index
    """
    # NOTE: normalize_for_matching() only removes ABBREVIATED prefixes (kel, ds, etc.),
    # not expanded ones (Kelurahan, Desa). So applying it to pre-normalized values
    # (from normalize_kelurahan_desa) is correct and matches the original script behavior.
    
    if prefix == 'detail':
        # Detail has combined kelurahan_desa_combined from exact matching
        # (created by combining kelurahan_normalized + desa_normalized)
        kel_col = 'kelurahan_desa_combined'
    else:
        # POS has desa_kelurahan_normalized
        kel_col = 'desa_kelurahan_normalized'
    
    # Both detail and POS use 'kabupaten_kota' for fuzzy matching
    # (This matches scoring_cascading_polars.py which uses same column for both)
    kab_col = 'kabupaten_kota'
    
    # Add fuzzy-normalized columns
    df = df.with_columns([
        pl.col('provinsi').map_elements(
            lambda x: normalize_for_matching(str(x) if x else '', 'province'),
            return_dtype=pl.Utf8
        ).alias('norm_prov'),
        pl.col(kab_col).map_elements(
            lambda x: normalize_for_matching(str(x) if x else '', 'kabupaten'),
            return_dtype=pl.Utf8
        ).alias('norm_kab'),
        pl.col('kecamatan').map_elements(
            lambda x: normalize_for_matching(str(x) if x else '', 'kecamatan'),
            return_dtype=pl.Utf8
        ).alias('norm_kec'),
        pl.col(kel_col).map_elements(
            lambda x: normalize_for_matching(str(x) if x else '', 'kelurahan'),
            return_dtype=pl.Utf8
        ).alias('norm_kel'),
    ])
    
    # Add row index
    df = df.with_row_index(f'{prefix}_idx')
    
    # Prefix data columns (keep index as is)
    data_columns = [c for c in df.columns if not c.endswith('_idx')]
    prefixed_columns = [pl.col(c).alias(f'{prefix}_{c}') for c in data_columns]
    df = df.select(prefixed_columns + [pl.col(f'{prefix}_idx')])
    
    return df
    
    
def _deduplicate_matches(matches_df: pl.DataFrame) -> pl.DataFrame:
    """
    Perform 1-to-1 deduplication using iterative greedy approach.
    
    Args:
        matches_df: DataFrame with potential matches and 'overall_conf' column
        
    Returns:
        Deduplicated DataFrame
    """
    print("\nPerforming 1-to-1 deduplication...")
    
    # Sort by confidence descending
    sorted_matches = matches_df.sort('overall_conf', descending=True)
    
    # Convert to dictionaries for iterative processing
    # This is necessary because Polars unique() is "local greedy" (drops second-best matches immediately),
    # whereas we need "global greedy" (if best match is taken, fall back to second best).
    potential_matches = sorted_matches.to_dicts()
    
    used_detail = set()
    used_pos = set()
    final_indices = []
    
    for i, match in enumerate(potential_matches):
        d_idx = match['detail_idx']
        p_idx = match['pos_idx']
        
        if d_idx not in used_detail and p_idx not in used_pos:
            used_detail.add(d_idx)
            used_pos.add(p_idx)
            final_indices.append(i)
            
    # Filter dataframe to keep only selected matches
    # We use the original sorted 'filtered' dataframe and select by row index
    return sorted_matches[final_indices]


def cascading_fuzzy_match(
    unmatched_detail_df: pl.DataFrame,
    unmapped_pos_df: pl.DataFrame
) -> Tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    """
    Perform cascading hierarchical fuzzy matching with hard gates.

    Each administrative level must independently pass its threshold.
    Implements 1-to-1 matching with strict deduplication.

    Args:
        unmatched_detail_df: Detail records not matched by exact join
        unmapped_pos_df: POS records not used in exact join

    Returns:
        Tuple of (matched_fuzzy_df, final_unmatched_detail_df, final_unmapped_pos_df)
    """
    print(f"\n=== Cascading Fuzzy Matching ===")
    print(f"Unmatched detail records: {len(unmatched_detail_df)}")
    print(f"Unmapped POS records: {len(unmapped_pos_df)}")

    if len(unmatched_detail_df) == 0 or len(unmapped_pos_df) == 0:
        print("No fuzzy matching needed (no unmatched records)")
        return pl.DataFrame(), unmatched_detail_df, unmapped_pos_df

    # Prepare dataframes and perform cross join
    joined = _prepare_and_join_dataframes(unmatched_detail_df, unmapped_pos_df)

    # Apply filtering and matching logic
    filtered = _apply_cascading_filters(joined)

    if len(filtered) == 0:
        print("No fuzzy matches passed all gates")
        return pl.DataFrame(), unmatched_detail_df, unmapped_pos_df

    # Perform 1-to-1 deduplication
    filtered = _deduplicate_matches(filtered)
    print(f"After deduplication: {len(filtered)} unique 1-to-1 matches")

    # Prepare results
    result = _prepare_final_results(filtered, unmatched_detail_df, unmapped_pos_df)
    return result


def _prepare_and_join_dataframes(
    unmatched_detail_df: pl.DataFrame,
    unmapped_pos_df: pl.DataFrame
) -> pl.DataFrame:
    """Prepare dataframes for fuzzy matching and perform cross join."""
    # Prepare dataframes for fuzzy matching
    detail_prep = prepare_for_fuzzy_matching(unmatched_detail_df, 'detail')
    pos_prep = prepare_for_fuzzy_matching(unmapped_pos_df, 'pos')

    total_pairs = len(detail_prep) * len(pos_prep)
    print(f"Total possible pairs: {total_pairs:,}")

    # Cross join
    print("Performing cross join...")
    joined = detail_prep.join(pos_prep, how='cross')

    # Calculate string similarities using polars-ds
    print("Computing string similarities...")
    joined = joined.with_columns([
        pds.str_jw(pl.col('detail_norm_prov'), pl.col('pos_norm_prov')).alias('prov_sim'),
        pds.str_jw(pl.col('detail_norm_kab'), pl.col('pos_norm_kab')).alias('kab_sim'),
        pds.str_jw(pl.col('detail_norm_kec'), pl.col('pos_norm_kec')).alias('kec_sim'),
        pds.str_jw(pl.col('detail_norm_kel'), pl.col('pos_norm_kel')).alias('kel_sim'),
    ])

    return joined


def _apply_cascading_filters(joined: pl.DataFrame) -> pl.DataFrame:
    """Apply cascading gate filters to the joined dataframe."""
    # Apply cascading gates
    print(f"Applying gates (Prov>={PROVINCE_THRESHOLD}, Kab>={KABUPATEN_THRESHOLD}, Kec>={KECAMATAN_THRESHOLD}, Kel>={KELURAHAN_THRESHOLD}, Overall>={OVERALL_THRESHOLD})...")

    filtered = joined.filter(pl.col('prov_sim') >= PROVINCE_THRESHOLD)
    print(f"  After Province gate: {len(filtered):,} pairs")

    filtered = filtered.filter(pl.col('kab_sim') >= KABUPATEN_THRESHOLD)
    print(f"  After Kabupaten gate: {len(filtered):,} pairs")

    filtered = filtered.filter(pl.col('kec_sim') >= KECAMATAN_THRESHOLD)
    print(f"  After Kecamatan gate: {len(filtered):,} pairs")

    filtered = filtered.filter(pl.col('kel_sim') >= KELURAHAN_THRESHOLD)
    print(f"  After Kelurahan gate: {len(filtered):,} pairs")

    # Calculate overall confidence and apply final gate
    filtered = filtered.with_columns(
        (KECAMATAN_WEIGHT * pl.col('kec_sim') + KELURAHAN_WEIGHT * pl.col('kel_sim')).alias('overall_conf')
    )
    filtered = filtered.filter(pl.col('overall_conf') >= OVERALL_THRESHOLD)
    print(f"  After Overall gate: {len(filtered):,} pairs")

    return filtered


def _prepare_final_results(
    filtered: pl.DataFrame,
    unmatched_detail_df: pl.DataFrame,
    unmapped_pos_df: pl.DataFrame
) -> Tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    """Prepare the final matched and unmatched dataframes."""
    # Prepare matched fuzzy dataframe
    # Reconstruct original detail structure with added POS data
    matched_fuzzy = filtered.select([
        # Detail columns (unprefixed)
        pl.col('detail_kode_kelurahan').alias('kode_kelurahan'),
        pl.col('detail_kabupaten_kota').alias('kabupaten_kota'),
        pl.col('detail_kecamatan').alias('kecamatan'),
        pl.col('detail_kelurahan_normalized').alias('kelurahan'),
        pl.col('detail_desa_normalized').alias('desa'),
        pl.col('detail_provinsi').alias('provinsi'),

        # POS data
        pl.col('pos_kodepos').alias('kodepos'),

        # Confidence scores
        pl.col('overall_conf').alias('overall_confidence'),
        pl.col('prov_sim').alias('provinsi_similarity'),
        pl.col('kab_sim').alias('kabupaten_similarity'),
        pl.col('kec_sim').alias('kecamatan_similarity'),
        pl.col('kel_sim').alias('kelurahan_similarity'),

        # Indices for tracking
        'detail_idx',
        'pos_idx'
    ])

    # Identify remaining unmatched records
    matched_detail_indices = set(filtered['detail_idx'].to_list())
    matched_pos_indices = set(filtered['pos_idx'].to_list())

    # Filter original unmatched dataframes
    final_unmatched_detail = unmatched_detail_df.with_row_index('temp_idx').filter(
        ~pl.col('temp_idx').is_in(matched_detail_indices)
    ).drop('temp_idx')

    final_unmapped_pos = unmapped_pos_df.with_row_index('temp_idx').filter(
        ~pl.col('temp_idx').is_in(matched_pos_indices)
    ).drop('temp_idx')

    print(f"Final unmatched detail records: {len(final_unmatched_detail)}")
    print(f"Final unmapped POS records: {len(final_unmapped_pos)}")

    return matched_fuzzy, final_unmatched_detail, final_unmapped_pos


# ============================================================================
# OUTPUT GENERATION HELPER FUNCTIONS
# ============================================================================

def _align_and_concat(
    dfs: List[pl.DataFrame],
    how: ConcatMethod = 'vertical'
) -> pl.DataFrame:
    """
    Align schemas and concatenate multiple DataFrames.
    
    Args:
        dfs: List of DataFrames to concatenate
        how: Concatenation method ('vertical' or 'horizontal')
        
    Returns:
        Concatenated DataFrame with aligned schemas
    """
    if not dfs:
        return pl.DataFrame()
    
    if len(dfs) == 1:
        return dfs[0]
    
    # Find common columns across all DataFrames
    common_columns = set(dfs[0].columns)
    for df in dfs[1:]:
        common_columns &= set(df.columns)
    
    common_columns = list(common_columns)
    
    # Select common columns from each DataFrame and concatenate
    return pl.concat(
        [df.select(common_columns) for df in dfs],
        how=how
    )


class DiagnosticColumnStrategy(ABC):
    """Abstract base class for preparing diagnostic columns."""

    @abstractmethod
    def prepare_columns(self, df: pl.DataFrame, kelurahan_col: str, desa_col: str) -> pl.DataFrame:
        """Prepare diagnostic columns for a specific match type."""
        pass


class ExactMatchStrategy(DiagnosticColumnStrategy):
    """Strategy for exact match records."""

    def prepare_columns(self, df: pl.DataFrame, kelurahan_col: str, desa_col: str) -> pl.DataFrame:
        """Prepare columns for exact matches (all similarities = 1.0)."""
        return df.select([
            # Base detail columns
            pl.col('kode_kelurahan').alias('detail_kode_kelurahan'),
            pl.col('provinsi').alias('detail_provinsi'),
            pl.col('kabupaten_kota').alias('detail_kabupaten_kota'),
            pl.col('kecamatan').alias('detail_kecamatan'),
            (pl.col(kelurahan_col).fill_null('') + pl.col(desa_col).fill_null('')).alias('detail_kelurahan_desa'),

            # Perfect similarity scores
            pl.lit(1.0).alias('overall_confidence'),
            pl.lit(1.0).alias('provinsi_similarity'),
            pl.lit(1.0).alias('kabupaten_similarity'),
            pl.lit(1.0).alias('kecamatan_similarity'),
            pl.lit(1.0).alias('kelurahan_similarity'),

            # POS columns
            pl.col('kodepos'),
            pl.col('provinsi').alias('pos_provinsi'),
            pl.col('kabupaten_kota').alias('pos_kabupaten_kota'),
            pl.col('kecamatan').alias('pos_kecamatan'),
            pl.col('kelurahan').alias('pos_kelurahan'),

            # Normalized columns
            pl.col('provinsi').alias('detail_provinsi_norm'),
            pl.col('kabupaten_kota').alias('detail_kabupaten_kota_norm'),
            pl.col('kecamatan').alias('detail_kecamatan_norm'),
            pl.col('kelurahan').alias('detail_kelurahan_norm'),
        ])


class FuzzyMatchStrategy(DiagnosticColumnStrategy):
    """Strategy for fuzzy match records."""

    def prepare_columns(self, df: pl.DataFrame, kelurahan_col: str, desa_col: str) -> pl.DataFrame:
        """Prepare columns for fuzzy matches with actual similarity scores."""
        return df.select([
            # Base detail columns
            pl.col('kode_kelurahan').alias('detail_kode_kelurahan'),
            pl.col('provinsi').alias('detail_provinsi'),
            pl.col('kabupaten_kota').alias('detail_kabupaten_kota'),
            pl.col('kecamatan').alias('detail_kecamatan'),
            (pl.col(kelurahan_col).fill_null('') + pl.col(desa_col).fill_null('')).alias('detail_kelurahan_desa'),

            # Actual similarity scores
            pl.col('overall_confidence'),
            pl.col('provinsi_similarity'),
            pl.col('kabupaten_similarity'),
            pl.col('kecamatan_similarity'),
            pl.col('kelurahan_similarity'),

            # POS columns
            pl.col('kodepos'),
            pl.col('provinsi').alias('pos_provinsi'),
            pl.col('kabupaten_kota').alias('pos_kabupaten_kota'),
            pl.col('kecamatan').alias('pos_kecamatan'),
            pl.col('kelurahan').alias('pos_kelurahan'),

            # Normalized columns
            pl.col('provinsi').alias('detail_provinsi_norm'),
            pl.col('kabupaten_kota').alias('detail_kabupaten_kota_norm'),
            pl.col('kecamatan').alias('detail_kecamatan_norm'),
            pl.col('kelurahan').alias('detail_kelurahan_norm'),
        ])


class UnmatchedStrategy(DiagnosticColumnStrategy):
    """Strategy for unmatched records."""

    def prepare_columns(self, df: pl.DataFrame, kelurahan_col: str, desa_col: str) -> pl.DataFrame:
        """Prepare columns for unmatched records (no POS data, zero similarities)."""
        return df.select([
            # Base detail columns
            pl.col('kode_kelurahan').alias('detail_kode_kelurahan'),
            pl.col('provinsi').alias('detail_provinsi'),
            pl.col('kabupaten_kota').alias('detail_kabupaten_kota'),
            pl.col('kecamatan').alias('detail_kecamatan'),
            pl.col('kelurahan_desa_combined').alias('detail_kelurahan_desa'),

            # Zero similarity scores
            pl.lit(0.0).alias('overall_confidence'),
            pl.lit(0.0).alias('provinsi_similarity'),
            pl.lit(0.0).alias('kabupaten_similarity'),
            pl.lit(0.0).alias('kecamatan_similarity'),
            pl.lit(0.0).alias('kelurahan_similarity'),

            # Null POS columns
            pl.lit(None).cast(pl.Utf8).alias('kodepos'),
            pl.lit(None).cast(pl.Utf8).alias('pos_provinsi'),
            pl.lit(None).cast(pl.Utf8).alias('pos_kabupaten_kota'),
            pl.lit(None).cast(pl.Utf8).alias('pos_kecamatan'),
            pl.lit(None).cast(pl.Utf8).alias('pos_kelurahan'),

            # Normalized columns
            pl.col('provinsi').alias('detail_provinsi_norm'),
            pl.col('kabupaten_kota').alias('detail_kabupaten_kota_norm'),
            pl.col('kecamatan').alias('detail_kecamatan_norm'),
            pl.col('kelurahan').alias('detail_kelurahan_norm'),
        ])


def _prepare_diagnostic_columns(
    df: pl.DataFrame,
    match_type: str,
    kelurahan_col: str = 'kelurahan',
    desa_col: str = 'desa'
) -> pl.DataFrame:
    """
    Prepare diagnostic columns for exact, fuzzy, or unmatched records.

    Args:
        df: Input DataFrame
        match_type: 'exact', 'fuzzy', or 'unmatched'
        kelurahan_col: Name of kelurahan column
        desa_col: Name of desa column

    Returns:
        DataFrame with standardized diagnostic columns
    """
    strategies = {
        'exact': ExactMatchStrategy(),
        'fuzzy': FuzzyMatchStrategy(),
        'unmatched': UnmatchedStrategy()
    }

    if match_type not in strategies:
        raise ValueError(f"Unknown match_type: {match_type}")

    return strategies[match_type].prepare_columns(df, kelurahan_col, desa_col)


# ============================================================================
# OUTPUT GENERATION FUNCTIONS
# ============================================================================

def save_parquet_with_pos(
    detail_df: pl.DataFrame,
    exact_matches: pl.DataFrame,
    fuzzy_matches: pl.DataFrame,
    unmatched_detail: pl.DataFrame,
    output_path: Path
) -> None:
    """
    Save combined exact and fuzzy matches to parquet file.
    
    Args:
        detail_df: Original detail dataframe
        exact_matches: Dataframe of exact matches
        fuzzy_matches: Dataframe of fuzzy matches
        unmatched_detail: Dataframe of unmatched detail records
        output_path: Path to save parquet file
    """
    # Combine exact and fuzzy matches using helper function
    dfs_to_combine = []
    if len(exact_matches) > 0:
        dfs_to_combine.append(exact_matches)
    if len(fuzzy_matches) > 0:
        dfs_to_combine.append(fuzzy_matches)
    
    combined = _align_and_concat(dfs_to_combine) if dfs_to_combine else pl.DataFrame()
    
    # Add unmatched records (no kodepos, no confidence)
    if len(unmatched_detail) > 0:
        # Prepare unmatched to match schema
        unmatched_to_add = unmatched_detail.drop([
            'kecamatan_normalized', 'kelurahan_normalized',
            'desa_normalized', 'kelurahan_desa_combined'
        ])
        # Add null columns for kodepos and overall_confidence
        unmatched_to_add = unmatched_to_add.with_columns([
            pl.lit(None).cast(pl.Utf8).alias('kodepos'),
            pl.lit(None).cast(pl.Float64).alias('overall_confidence')
        ])
        
        # Combine with matched records
        if len(combined) > 0:
            final_df = _align_and_concat([combined, unmatched_to_add])
        else:
            final_df = unmatched_to_add
    elif len(combined) > 0:
        final_df = combined
    else:
        # No matches at all, return original detail with null postal codes
        final_df = detail_df.with_columns([
            pl.lit(None).cast(pl.Utf8).alias('kodepos'),
            pl.lit(None).cast(pl.Float64).alias('overall_confidence')
        ])
    
    # Save to parquet
    output_path.parent.mkdir(parents=True, exist_ok=True)
    final_df.write_parquet(output_path, compression='snappy')
    print(f"Saved {len(final_df)} records to {output_path}")


def save_diagnostic_csv(
    exact_matches: pl.DataFrame,
    fuzzy_matches: pl.DataFrame,
    unmatched_detail: pl.DataFrame,
    output_path: Path
) -> None:
    """
    Save diagnostic CSV with detailed similarity scores.

    Args:
        exact_matches: Dataframe of exact matches
        fuzzy_matches: Dataframe of fuzzy matches
        unmatched_detail: Dataframe of unmatched detail records
        output_path: Path to save CSV file
    """
    dfs_to_concat = []
    
    # Common columns for output
    cols = [
        'detail_kode_kelurahan', 'detail_provinsi', 'detail_kabupaten_kota',
        'detail_kecamatan', 'detail_kelurahan_desa',
        'overall_confidence',
        'provinsi_similarity', 'kabupaten_similarity', 'kecamatan_similarity', 'kelurahan_similarity',
        'pos_provinsi', 'pos_kabupaten_kota', 'pos_kecamatan', 'pos_kelurahan_desa', 'pos_kodepos'
    ]
    
    # 1. Process Exact Matches
    if len(exact_matches) > 0:
        exact_df = _prepare_diagnostic_columns(exact_matches, 'exact').select(cols)
        dfs_to_concat.append(exact_df)
        
    # 2. Process Fuzzy Matches
    if len(fuzzy_matches) > 0:
        fuzzy_df = _prepare_diagnostic_columns(fuzzy_matches, 'fuzzy').select(cols)
        dfs_to_concat.append(fuzzy_df)
        
    # 3. Process Unmatched Records
    if len(unmatched_detail) > 0:
        unmatched_df = _prepare_diagnostic_columns(unmatched_detail, 'unmatched').select(cols)
        dfs_to_concat.append(unmatched_df)
    
    if dfs_to_concat:
        concat_method: ConcatMethod = 'vertical'
        final_df = pl.concat(dfs_to_concat, how=concat_method)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        final_df.write_csv(output_path)
        print(f"Saved {len(final_df)} diagnostic records to {output_path}")


def save_unmapped_pos_parquet(
    unmapped_pos: pl.DataFrame,
    output_path: Path
) -> None:
    """
    Save unmapped POS records to parquet file.
    
    Args:
        unmapped_pos: Dataframe of unmapped POS records
        output_path: Path to save parquet file
    """
    if len(unmapped_pos) == 0:
        print("No unmapped POS records to save")
        return
    
    # Select relevant columns
    output_df = unmapped_pos.select([
        pl.col('provinsi'),
        pl.col('kabupaten_kota_source').alias('kabupaten_kota'),
        pl.col('kecamatan'),
        pl.col('desa_kelurahan_normalized').alias('kelurahan_desa'),
        pl.col('kodepos')
    ])
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_df.write_parquet(output_path, compression='snappy')
    print(f"Saved {len(output_df)} unmapped POS records to {output_path}")
