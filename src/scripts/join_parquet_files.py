#!/usr/bin/env python3
"""
Parquet Join Script - Join kabupaten_kota_detail and kabupaten_kota_pos files

This script joins detail and postal code parquet files, adding kodepos to the detail data.
It logs unmatched records from both sides for validation.
"""

import os
import glob
import sys
from typing import List, Tuple
from pathlib import Path

# Add src directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import polars as pl

# Import normalization functions
from utils.text_utils import normalize_kecamatan, normalize_kelurahan_desa


class ParquetJoiner:
    """Join detail and pos parquet files with comprehensive logging."""
    
    def __init__(self, parquet_dir: str = "src/output/parquet"):
        """
        Initialize the joiner.
        
        Args:
            parquet_dir: Base directory containing parquet files
        """
        self.parquet_dir = parquet_dir
        self.log_dir = os.path.join("src", "log")
        os.makedirs(self.log_dir, exist_ok=True)
        self.log_file = os.path.join(self.log_dir, "parquet_join.csv")
        
        # Clear log file and write CSV header
        with open(self.log_file, 'w', encoding='utf-8') as f:
            f.write("province,kabupaten_kota,kecamatan,kode_kelurahan,kelurahan_desa,kodepos,source\n")
    
    def join_province(self, province: str) -> dict:
        """
        Join detail and pos files for a single province.
        
        Args:
            province: Province name (e.g., 'aceh')
            
        Returns:
            Dict with statistics
        """
        detail_file = os.path.join(self.parquet_dir, province, f"{province}_kabupaten_kota_detail.parquet")
        pos_file = os.path.join(self.parquet_dir, province, f"{province}_kabupaten_kota_pos.parquet")
        output_file = os.path.join(self.parquet_dir, province, f"{province}_kabupaten_kota_with_pos.parquet")
        
        # Check if files exist
        if not os.path.exists(detail_file):
            print(f"WARNING: Detail file not found: {detail_file}")
            return {"status": "skipped", "reason": "detail_file_missing"}
        
        if not os.path.exists(pos_file):
            print(f"WARNING: Pos file not found: {pos_file}")
            return {"status": "skipped", "reason": "pos_file_missing"}
        
        print(f"\n{'='*80}")
        print(f"Processing: {province}")
        print(f"{'='*80}")
        
        # Read files
        df_detail = pl.read_parquet(detail_file)
        df_pos = pl.read_parquet(pos_file)
        
        print(f"Detail records: {len(df_detail):,}")
        print(f"Pos records: {len(df_pos):,}")
        
        # Prepare detail dataframe following data_merger logic:
        # 1. Filter out records with empty kode_kelurahan (line 210 in data_merger.py)
        # 2. Normalize kelurahan and desa columns (line 211 in data_merger.py)
        # 3. Create unified column by concatenating kelurahan + desa
        
        # Step 1: Filter by kode_kelurahan
        df_detail_filtered = df_detail.filter(
            (pl.col('kode_kelurahan').is_not_null()) &
            (pl.col('kode_kelurahan') != '')
        )
        
        print(f"Detail records after kode_kelurahan filter: {len(df_detail_filtered):,}")
        
        # Step 2: Normalize kelurahan and desa columns
        df_detail_filtered = df_detail_filtered.with_columns([
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
        
        # Step 3: Create unified kelurahan_desa column by concatenating
        # (one will be empty, the other filled)
        df_detail_filtered = df_detail_filtered.with_columns(
            kelurahan_desa_combined=(pl.col('kelurahan_normalized') + pl.col('desa_normalized'))
        )
        
        # Filter to only records with complete hierarchy
        df_detail_complete = df_detail_filtered.filter(
            (pl.col('kecamatan_normalized') != '') &
            (pl.col('kelurahan_desa_combined') != '')
        )
        
        print(f"Detail records with complete hierarchy: {len(df_detail_complete):,}")
        
        # Prepare pos dataframe - apply same normalization
        df_pos = df_pos.with_columns([
            pl.col('kecamatan').map_elements(
                lambda x: normalize_kecamatan(x) if x else "",
                return_dtype=pl.Utf8
            ).alias('kecamatan_normalized'),
            pl.col('desa_kelurahan').map_elements(
                lambda x: normalize_kelurahan_desa(x) if x else "",
                return_dtype=pl.Utf8
            ).alias('desa_kelurahan_normalized')
        ])
        
        # Perform left join on normalized columns
        df_joined = df_detail_complete.join(
            df_pos.select(['kabupaten_kota_source', 'kecamatan_normalized', 'desa_kelurahan_normalized', 'kodepos']),
            left_on=['kabupaten_kota', 'kecamatan_normalized', 'kelurahan_desa_combined'],
            right_on=['kabupaten_kota_source', 'kecamatan_normalized', 'desa_kelurahan_normalized'],
            how='left'
        )
        
        # Note: Keep normalized columns for logging, will drop before saving
        
        # Identify matched and unmatched records
        matched = df_joined.filter(pl.col('kodepos').is_not_null())
        unmatched_detail = df_joined.filter(pl.col('kodepos').is_null())
        
        # Identify unmapped pos records (anti-join)
        # These are pos records that don't match any detail record
        unmapped_pos = df_pos.join(
            df_detail_complete.select(['kabupaten_kota', 'kecamatan_normalized', 'kelurahan_desa_combined']),
            left_on=['kabupaten_kota_source', 'kecamatan_normalized', 'desa_kelurahan_normalized'],
            right_on=['kabupaten_kota', 'kecamatan_normalized', 'kelurahan_desa_combined'],
            how='anti'
        )
        
        # Log unmatched records
        self._log_unmatched_detail(province, unmatched_detail)
        self._log_unmapped_pos(province, unmapped_pos)
        
        # Drop normalized helper columns before saving
        df_output = df_joined.drop(['kecamatan_normalized', 'kelurahan_normalized', 'desa_normalized', 'kelurahan_desa_combined'])
        
        # Save joined data
        df_output.write_parquet(output_file)
        
        # Statistics
        stats = {
            "status": "success",
            "province": province,
            "total_detail_records": len(df_detail),
            "total_pos_records": len(df_pos),
            "matched_records": len(matched),
            "unmatched_detail_records": len(unmatched_detail),
            "unmapped_pos_records": len(unmapped_pos),
            "match_rate": f"{(len(matched) / len(df_detail) * 100):.2f}%",
            "output_file": output_file
        }
        
        print(f"\nStatistics:")
        print(f"  Matched (with kodepos): {stats['matched_records']:,} ({stats['match_rate']})")
        print(f"  Unmatched detail (no kodepos): {stats['unmatched_detail_records']:,}")
        print(f"  Unmapped pos (not in detail): {stats['unmapped_pos_records']:,}")
        print(f"  Output: {output_file}")
        
        return stats
    
    def _log_unmatched_detail(self, province: str, unmatched: pl.DataFrame):
        """Log detail records that don't have postal codes to CSV."""
        if len(unmatched) == 0:
            return
        
        with open(self.log_file, 'a', encoding='utf-8') as f:
            for row in unmatched.select([
                'kabupaten_kota', 'kecamatan', 'kelurahan', 'desa', 'kode_kelurahan',
                'kelurahan_normalized', 'desa_normalized'
            ]).iter_rows(named=True):
                # Use normalized kelurahan_desa (concatenated, with leading numbers stripped)
                kelurahan_desa_normalized = (row['kelurahan_normalized'] or '') + (row['desa_normalized'] or '')
                
                # CSV format: province,kabupaten_kota,kecamatan,kode_kelurahan,kelurahan_desa,kodepos,source
                f.write(f"{province},{row['kabupaten_kota']},{row['kecamatan']},{row['kode_kelurahan']},{kelurahan_desa_normalized},,detail\n")
    
    def _log_unmapped_pos(self, province: str, unmapped: pl.DataFrame):
        """Log pos records that don't match any detail record to CSV."""
        if len(unmapped) == 0:
            return
        
        with open(self.log_file, 'a', encoding='utf-8') as f:
            for row in unmapped.select([
                'kabupaten_kota_source', 'kecamatan', 'desa_kelurahan', 'kodepos',
                'desa_kelurahan_normalized'
            ]).iter_rows(named=True):
                # Use normalized desa_kelurahan
                kelurahan_desa_normalized = row['desa_kelurahan_normalized'] or ''
                
                # CSV format: province,kabupaten_kota,kecamatan,kode_kelurahan,kelurahan_desa,kodepos,source
                f.write(f"{province},{row['kabupaten_kota_source']},{row['kecamatan']},,{kelurahan_desa_normalized},{row['kodepos']},pos\n")
    
    def join_all_provinces(self) -> List[dict]:
        """
        Join all provinces found in the parquet directory.
        
        Returns:
            List of statistics for each province
        """
        # Find all province directories
        province_dirs = glob.glob(os.path.join(self.parquet_dir, '*', ''))
        provinces = [os.path.basename(os.path.dirname(d)) for d in province_dirs]
        provinces = [p for p in provinces if not p.startswith('indonesia')]  # Skip merged file
        provinces.sort()
        
        print(f"\nFound {len(provinces)} provinces to process")
        
        all_stats = []
        for province in provinces:
            stats = self.join_province(province)
            all_stats.append(stats)
        
        # Summary
        print(f"\n{'='*80}")
        print("SUMMARY")
        print(f"{'='*80}")
        
        successful = [s for s in all_stats if s.get('status') == 'success']
        skipped = [s for s in all_stats if s.get('status') == 'skipped']
        
        print(f"Successfully processed: {len(successful)}")
        print(f"Skipped: {len(skipped)}")
        
        if successful:
            total_detail = sum(s['total_detail_records'] for s in successful)
            total_matched = sum(s['matched_records'] for s in successful)
            total_unmatched_detail = sum(s['unmatched_detail_records'] for s in successful)
            total_unmapped_pos = sum(s['unmapped_pos_records'] for s in successful)
            
            print(f"\nOverall Statistics:")
            print(f"  Total detail records: {total_detail:,}")
            print(f"  Matched (with kodepos): {total_matched:,} ({total_matched/total_detail*100:.2f}%)")
            print(f"  Unmatched detail: {total_unmatched_detail:,}")
            print(f"  Unmapped pos: {total_unmapped_pos:,}")
        
        print(f"\nDetailed log: {self.log_file}")
        
        return all_stats


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Join detail and pos parquet files')
    parser.add_argument('--province', type=str, help='Specific province to process')
    parser.add_argument('--parquet-dir', type=str, default='src/output/parquet',
                       help='Base parquet directory (default: src/output/parquet)')
    
    args = parser.parse_args()
    
    joiner = ParquetJoiner(parquet_dir=args.parquet_dir)
    
    if args.province:
        stats = joiner.join_province(args.province)
        if stats.get('status') == 'success':
            print(f"\nSuccessfully joined {args.province}")
        else:
            print(f"\nFailed to join {args.province}: {stats.get('reason')}")
    else:
        joiner.join_all_provinces()


if __name__ == "__main__":
    main()
