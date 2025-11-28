"""
Postal Code Matching Utilities

This module provides functions for matching detail and POS records using both
exact normalized string matching and cascading fuzzy hierarchical matching.

Combines logic from join_parquet_files.py (exact matching) and 
scoring_cascading_polars.py (fuzzy matching) into reusable utility functions.
"""

import polars as pl
import polars_ds as pds
from pathlib import Path
from typing import Tuple, List, Dict, Any

from utils.text_utils import normalize_kecamatan, normalize_kelurahan_desa, normalize_for_matching


# Fuzzy matching thresholds (from scoring_cascading_polars.py)
PROVINCE_THRESHOLD = 0.95
KABUPATEN_THRESHOLD = 0.95
KECAMATAN_THRESHOLD = 0.75
KELURAHAN_THRESHOLD = 0.70
OVERALL_THRESHOLD = 0.80


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
        ).alias('kelurahan_normalized'),
        pl.col('desa').map_elements(
            lambda x: normalize_kelurahan_desa(x) if x else "", 
            return_dtype=pl.Utf8
        ).alias('desa_normalized'),
        pl.col('kecamatan').map_elements(
            lambda x: normalize_kecamatan(x) if x else "", 
            return_dtype=pl.Utf8
        ).alias('kecamatan_normalized')
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
        ).alias('kecamatan_normalized'),
        pl.col('desa_kelurahan').map_elements(
            lambda x: normalize_kelurahan_desa(x) if x else "", 
            return_dtype=pl.Utf8
        ).alias('desa_kelurahan_normalized')
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
    
    Args:
        df: Input dataframe (detail or pos)
        prefix: Prefix for columns ('detail' or 'pos')
        
    Returns:
        DataFrame with normalized fuzzy-matching columns and row index
    """
    # Determine column names based on source
    if prefix == 'detail':
        # Detail has combined kelurahan_desa_combined from exact matching
        kel_col = 'kelurahan_desa_combined'
    else:
        # POS has desa_kelurahan_normalized
        kel_col = 'desa_kelurahan_normalized'
    
    # Add fuzzy-normalized columns
    df = df.with_columns([
        pl.col('provinsi').map_elements(
            lambda x: normalize_for_matching(str(x), 'province'),
            return_dtype=pl.Utf8
        ).alias('norm_prov'),
        pl.col('kabupaten_kota' if prefix == 'detail' else 'kabupaten_kota_source').map_elements(
            lambda x: normalize_for_matching(str(x), 'kabupaten'),
            return_dtype=pl.Utf8
        ).alias('norm_kab'),
        pl.col('kecamatan').map_elements(
            lambda x: normalize_for_matching(str(x), 'kecamatan'),
            return_dtype=pl.Utf8
        ).alias('norm_kec'),
        pl.col(kel_col).map_elements(
            lambda x: normalize_for_matching(str(x), 'kelurahan'),
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
    
    # Apply cascading gates
    print(f"Applying gates (Prov≥{PROVINCE_THRESHOLD}, Kab≥{KABUPATEN_THRESHOLD}, Kec≥{KECAMATAN_THRESHOLD}, Kel≥{KELURAHAN_THRESHOLD}, Overall≥{OVERALL_THRESHOLD})...")
    
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
        (0.4 * pl.col('kec_sim') + 0.6 * pl.col('kel_sim')).alias('overall_conf')
    )
    filtered = filtered.filter(pl.col('overall_conf') >= OVERALL_THRESHOLD)
    print(f"  After Overall gate: {len(filtered):,} pairs")
    
    if len(filtered) == 0:
        print("No fuzzy matches passed all gates")
        return pl.DataFrame(), unmatched_detail_df, unmapped_pos_df
    
    # Perform 1-to-1 deduplication
    print("\nPerforming 1-to-1 deduplication...")
    filtered = filtered.sort('overall_conf', descending=True)
    
    # Deduplicate on detail side (keep best match per detail record)
    filtered = filtered.unique(subset=['detail_idx'], keep='first')
    
    # Deduplicate on POS side (keep best match per POS record)  
    filtered = filtered.unique(subset=['pos_idx'], keep='first')
    
    print(f"After deduplication: {len(filtered)} unique 1-to-1 matches")
    
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
    # Combine exact and fuzzy matches
    if len(exact_matches) > 0 and len(fuzzy_matches) > 0:
        # Align schemas
        common_columns = list(set(exact_matches.columns) & set(fuzzy_matches.columns))
        combined = pl.concat([
            exact_matches.select(common_columns),
            fuzzy_matches.select(common_columns)
        ], how='vertical')
    elif len(exact_matches) > 0:
        combined = exact_matches
    elif len(fuzzy_matches) > 0:
        combined = fuzzy_matches
    else:
        combined = pl.DataFrame()
    
    # Add unmatched records (no kodepos, no confidence)
    if len(combined) > 0 and len(unmatched_detail) > 0:
        # Prepare unmatched to match schema
        unmatched_to_add = unmatched_detail.drop([
            'kecamatan_normalized', 'kelurahan_normalized',
            'desa_normalized', 'kelurahan_desa_combined'
        ])
        # Add null columns for kodepos and overall_confidence if they don't exist
        if 'kodepos' not in unmatched_to_add.columns:
            unmatched_to_add = unmatched_to_add.with_columns(pl.lit(None).cast(pl.Utf8).alias('kodepos'))
        if 'overall_confidence' not in unmatched_to_add.columns:
            unmatched_to_add = unmatched_to_add.with_columns(pl.lit(None).cast(pl.Float64).alias('overall_confidence'))
        
        # Align schemas and concatenate
        common_columns_with_unmatched = list(set(combined.columns) & set(unmatched_to_add.columns))
        final_df = pl.concat([
            combined.select(common_columns_with_unmatched),
            unmatched_to_add.select(common_columns_with_unmatched)
        ], how='vertical')
    elif len(combined) > 0:
        final_df = combined
    elif len(unmatched_detail) > 0:
        unmatched_to_add = unmatched_detail.drop([
            'kecamatan_normalized', 'kelurahan_normalized',
            'desa_normalized', 'kelurahan_desa_combined'
        ])
        unmatched_to_add = unmatched_to_add.with_columns([
            pl.lit(None).cast(pl.Utf8).alias('kodepos'),
            pl.lit(None).cast(pl.Float64).alias('overall_confidence')
        ])
        final_df = unmatched_to_add
    else:
        final_df = detail_df.with_columns([
            pl.lit(None).cast(pl.Utf8).alias('kodepos'),
            pl.lit(None).cast(pl.Float64).alias('overall_confidence')
        ])
    
    # Save to parquet
    output_path.parent.mkdir(parents=True, exist_ok=True)
    final_df.write_parquet(output_path, compression='snappy')
    print(f"Saved {len(final_df)} records to {output_path}")


def save_diagnostic_parquet(
    exact_matches: pl.DataFrame,
    fuzzy_matches: pl.DataFrame,
    unmatched_detail: pl.DataFrame,
    output_path: Path
) -> None:
    """
    Save diagnostic parquet with detailed similarity scores.
    
    Args:
        exact_matches: Dataframe of exact matches
        fuzzy_matches: Dataframe of fuzzy matches
        unmatched_detail: Dataframe of unmatched detail records
        output_path: Path to save parquet file
    """
    # Build diagnostic records list
    records = []
    
    # Add exact matches
    for row in exact_matches.iter_rows(named=True):
        records.append({
            'detail_kode_kelurahan': row.get('kode_kelurahan', ''),
            'detail_provinsi': row.get('provinsi', ''),
            'detail_kabupaten_kota': row.get('kabupaten_kota', ''),
            'detail_kecamatan': row.get('kecamatan', ''),
            'detail_kelurahan_desa': f"{row.get('kelurahan', '')}{row.get('desa', '')}",
            'overall_confidence': 1.0,
            'provinsi_similarity': 1.0,
            'kabupaten_similarity': 1.0,
            'kecamatan_similarity': 1.0,
            'kelurahan_similarity': 1.0,
            'pos_provinsi': row.get('provinsi', ''),
            'pos_kabupaten_kota': row.get('kabupaten_kota', ''),
            'pos_kecamatan': row.get('kecamatan', ''),
            'pos_kelurahan_desa': f"{row.get('kelurahan', '')}{row.get('desa', '')}",
            'pos_kodepos': row.get('kodepos', '')
        })
    
    # Add fuzzy matches
    for row in fuzzy_matches.iter_rows(named=True):
        records.append({
            'detail_kode_kelurahan': row.get('kode_kelurahan', ''),
            'detail_provinsi': row.get('provinsi', ''),
            'detail_kabupaten_kota': row.get('kabupaten_kota', ''),
            'detail_kecamatan': row.get('kecamatan', ''),
            'detail_kelurahan_desa': f"{row.get('kelurahan', '')}{row.get('desa', '')}",
            'overall_confidence': row.get('overall_confidence', 0.0),
            'provinsi_similarity': row.get('provinsi_similarity', 0.0),
            'kabupaten_similarity': row.get('kabupaten_similarity', 0.0),
            'kecamatan_similarity': row.get('kecamatan_similarity', 0.0),
            'kelurahan_similarity': row.get('kelurahan_similarity', 0.0),
            'pos_provinsi': row.get('provinsi', ''),
            'pos_kabupaten_kota': row.get('kabupaten_kota', ''),
            'pos_kecamatan': row.get('kecamatan', ''),
            'pos_kelurahan_desa': f"{row.get('kelurahan', '')}{row.get('desa', '')}",
            'pos_kodepos': row.get('kodepos', '')
        })
    
    # Add unmatched records
    for row in unmatched_detail.iter_rows(named=True):
        records.append({
            'detail_kode_kelurahan': row.get('kode_kelurahan', ''),
            'detail_provinsi': row.get('provinsi', ''),
            'detail_kabupaten_kota': row.get('kabupaten_kota', ''),
            'detail_kecamatan': row.get('kecamatan', ''),
            'detail_kelurahan_desa': row.get('kelurahan_desa_combined', ''),
            'overall_confidence': 0.0,
            'provinsi_similarity': 0.0,
            'kabupaten_similarity': 0.0,
            'kecamatan_similarity': 0.0,
            'kelurahan_similarity': 0.0,
            'pos_provinsi': '',
            'pos_kabupaten_kota': '',
            'pos_kecamatan': '',
            'pos_kelurahan_desa': '',
            'pos_kodepos': ''
        })
    
    if records:
        df = pl.DataFrame(records)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        df.write_parquet(output_path, compression='snappy')
        print(f"Saved {len(df)} diagnostic records to {output_path}")


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
