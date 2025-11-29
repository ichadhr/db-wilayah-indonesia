#!/usr/bin/env python3
"""
Unified Postal Code Matching Pipeline

This script combines exact normalized string matching and cascading fuzzy 
hierarchical matching into a single pipeline. It processes province data
in two stages:

1. Exact Matching: Fast normalized string matching on kecamatan/kelurahan
2. Fuzzy Matching: Hierarchical similarity matching on remaining unmatched records

Output files (with _new suffix):
- {province}_kabupaten_kota_with_pos_new.parquet: All detail records with postal codes
- {province}_cascading_matches_new.csv: Diagnostic file with similarity scores
- {province}_cascading_matches_remain_new.parquet: Unmapped POS records
"""

import sys
import argparse
from pathlib import Path
from typing import Tuple

# Add src directory to path
src_dir = Path(__file__).parent.parent
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

import polars as pl

from utils.matcher import (
    normalize_detail_data,
    normalize_pos_data,
    perform_exact_join,
    cascading_fuzzy_match,
    save_parquet_with_pos,
    save_diagnostic_csv,
    save_unmapped_pos_parquet
)


class Config:
    """Configuration for postal code matching."""
    DEFAULT_PARQUET_DIR = "src/output/parquet"
    LOG_DIR = "src/log"
    DETAIL_SUFFIX = "_kabupaten_kota_detail.parquet"
    POS_SUFFIX = "_kabupaten_kota_pos.parquet"


def load_parquet_files(province: str, parquet_dir: Path) -> Tuple[pl.DataFrame, pl.DataFrame]:
    """
    Load detail and POS parquet files for a province.
    
    Args:
        province: Province name
        parquet_dir: Base directory containing province subdirectories
        
    Returns:
        Tuple of (detail_df, pos_df)
    """
    province_dir = parquet_dir / province
    detail_file = province_dir / f"{province}{Config.DETAIL_SUFFIX}"
    pos_file = province_dir / f"{province}{Config.POS_SUFFIX}"
    
    if not detail_file.exists():
        raise FileNotFoundError(f"Detail file not found: {detail_file}")
    if not pos_file.exists():
        raise FileNotFoundError(f"POS file not found: {pos_file}")
    
    print(f"\n{'='*80}")
    print(f"Processing: {province}")
    print(f"{'='*80}\n")
    
    detail_df = pl.read_parquet(detail_file)
    pos_df = pl.read_parquet(pos_file)
    
    print(f"Loaded {len(detail_df):,} detail records")
    print(f"Loaded {len(pos_df):,} POS records")
    
    return detail_df, pos_df


def match_province(province: str, parquet_dir: Path, log_dir: Path) -> None:
    """
    Run complete matching pipeline for a single province.
    
    Args:
        province: Province name
        parquet_dir: Base directory containing input parquet files
        log_dir: Base directory for output files
    """
    try:
        # Step 1: Load data
        detail_df, pos_df = load_parquet_files(province, parquet_dir)
        
        # Step 2: Normalize and perform exact matching
        print("\n=== Stage 1: Exact Matching ===")
        detail_normalized = normalize_detail_data(detail_df, province)
        pos_normalized = normalize_pos_data(pos_df, province)
        
        print(f"Detail normalized: {len(detail_normalized):,} records")
        
        exact_matches, unmatched_detail, unmapped_pos = perform_exact_join(
            detail_normalized,
            pos_normalized
        )
        
        print(f"Exact matches: {len(exact_matches):,}")
        print(f"Unmatched detail records: {len(unmatched_detail):,}")
        print(f"Unmapped POS records: {len(unmapped_pos):,}")
        
        # Step 3: Fuzzy matching on remaining unmatched records
        print("\n=== Stage 2: Fuzzy Matching ===")
        if len(unmatched_detail) > 0 and len(unmapped_pos) > 0:
            fuzzy_matches, final_unmatched_detail, final_unmapped_pos = cascading_fuzzy_match(
                unmatched_detail,
                unmapped_pos
            )
        else:
            print("Skipping fuzzy matching (no unmatched records)")
            fuzzy_matches = pl.DataFrame()
            final_unmatched_detail = unmatched_detail
            final_unmapped_pos = unmapped_pos
        
        # Step 4: Save outputs
        print("\n=== Saving Outputs ===")
        province_log_dir = log_dir / province
        province_log_dir.mkdir(parents=True, exist_ok=True)
        
        # Output 1: Combined parquet with postal codes
        save_parquet_with_pos(
            detail_normalized,
            exact_matches,
            fuzzy_matches,
            final_unmatched_detail,
            province_log_dir / f"{province}_kabupaten_kota_with_pos_new.parquet"
        )
        
        # Output 2: Diagnostic CSV with similarity scores
        save_diagnostic_csv(
            exact_matches,
            fuzzy_matches,
            final_unmatched_detail,
            province_log_dir / f"{province}_cascading_matches_new.csv"
        )
        
        # Output 3: Unmapped POS records
        save_unmapped_pos_parquet(
            final_unmapped_pos,
            province_log_dir / f"{province}_cascading_matches_remain_new.parquet"
        )
        
        # Print summary statistics
        # Use detail_normalized (after kode_kelurahan filter) as the true total
        total_detail = len(detail_normalized)
        total_matched = len(exact_matches) + len(fuzzy_matches)
        match_rate = (total_matched / total_detail * 100) if total_detail > 0 else 0
        
        print(f"\n{'='*80}")
        print(f"SUMMARY: {province}")
        print(f"{'='*80}")
        print(f"Total detail records: {total_detail:,}")
        print(f"Exact matches: {len(exact_matches):,} ({len(exact_matches)/total_detail*100:.1f}%)")
        print(f"Fuzzy matches: {len(fuzzy_matches):,} ({len(fuzzy_matches)/total_detail*100:.1f}%)")
        print(f"Total matched: {total_matched:,} ({match_rate:.1f}%)")
        print(f"Unmatched: {len(final_unmatched_detail):,} ({len(final_unmatched_detail)/total_detail*100:.1f}%)")
        print(f"{'='*80}\n")
        
    except Exception as e:
        import traceback
        print(f"\n{'='*80}")
        print(f"ERROR processing {province}")
        print(f"{'='*80}")
        print(traceback.format_exc())
        raise


def main():
    """Main entry point with CLI argument parsing."""
    parser = argparse.ArgumentParser(
        description='Unified Postal Code Matching Pipeline',
        epilog='Combines exact and fuzzy matching for accurate postal code assignment'
    )
    parser.add_argument('--province', type=str, help='Specific province to process')
    parser.add_argument('--parquet-dir', type=str, default=Config.DEFAULT_PARQUET_DIR,
                       help=f'Base parquet directory (default: {Config.DEFAULT_PARQUET_DIR})')
    parser.add_argument('--log-dir', type=str, default=Config.LOG_DIR,
                       help=f'Output log directory (default: {Config.LOG_DIR})')
    
    args = parser.parse_args()
    
    # Resolve paths
    script_dir = Path(__file__).parent
    project_root = script_dir.parent.parent
    
    parquet_dir = Path(args.parquet_dir)
    if not parquet_dir.is_absolute():
        parquet_dir = project_root / args.parquet_dir
    
    log_dir = Path(args.log_dir)
    if not log_dir.is_absolute():
        log_dir = project_root / args.log_dir
    
    if args.province:
        # Process single province
        match_province(args.province, parquet_dir, log_dir)
    else:
        # Process all provinces
        province_dirs = [d for d in parquet_dir.iterdir() if d.is_dir()]
        provinces = [
            d.name for d in province_dirs 
            if not d.name.startswith('indonesia')  # Skip merged files
        ]
        provinces.sort()
        
        print(f"\nFound {len(provinces)} provinces to process: {', '.join(provinces)}\n")
        
        successful = 0
        failed = []
        
        for province in provinces:
            try:
                match_province(province, parquet_dir, log_dir)
                successful += 1
            except Exception as e:
                print(f"FAILED: {province} - {e}\n")
                failed.append(province)
        
        # Final summary
        print(f"\n{'='*80}")
        print("FINAL SUMMARY")
        print(f"{'='*80}")
        print(f"Successfully processed: {successful}/{len(provinces)}")
        if failed:
            print(f"Failed provinces: {', '.join(failed)}")
        print(f"{'='*80}\n")


if __name__ == "__main__":
    main()
