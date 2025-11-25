#!/usr/bin/env python3
"""
Parquet Join Script - Join kabupaten_kota_detail and kabupaten_kota_pos files

This script joins detail and postal code parquet files, adding kodepos to the detail data.
It logs unmatched records from both sides for validation.
"""

import sys
import concurrent.futures
import threading
from typing import List, Optional, Dict, Any
from pathlib import Path

# Add src directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import polars as pl

# Type aliases
DataFrame = pl.DataFrame
LazyFrame = pl.LazyFrame
StatsDict = Dict[str, Any]


class Config:
    """Configuration class for ParquetJoiner settings."""

    # Directory settings
    DEFAULT_PARQUET_DIR = "src/output/parquet"
    LOG_DIR = "src/log"

    # File suffixes
    DETAIL_SUFFIX = "_kabupaten_kota_detail.parquet"
    POS_SUFFIX = "_kabupaten_kota_pos.parquet"
    OUTPUT_SUFFIX = "_kabupaten_kota_with_pos.parquet"

    # Log file settings
    LOG_SUFFIX = "_parquet_join.csv"
    DEFAULT_LOG_FILE = "parquet_join.csv"

    # Output settings
    COMPRESSION = 'snappy'
    ROW_GROUP_SIZE = 50000


class ParquetJoiner:
    """Join detail and pos parquet files with comprehensive logging."""
    # File naming patterns
    DETAIL_SUFFIX = "_kabupaten_kota_detail.parquet"
    POS_SUFFIX = "_kabupaten_kota_pos.parquet"
    OUTPUT_SUFFIX = "_kabupaten_kota_with_pos.parquet"

    # Column names
    KODE_KELURAHAN = 'kode_kelurahan'
    KABUPATEN_KOTA = 'kabupaten_kota'
    KECAMATAN = 'kecamatan'
    KELURAHAN = 'kelurahan'
    DESA = 'desa'
    KODEPOS = 'kodepos'
    KABUPATEN_KOTA_SOURCE = 'kabupaten_kota_source'
    DESA_KELURAHAN = 'desa_kelurahan'
    KECAMATAN_NORMALIZED = 'kecamatan_normalized'
    KELURAHAN_NORMALIZED = 'kelurahan_normalized'
    DESA_NORMALIZED = 'desa_normalized'
    KELURAHAN_DESA_COMBINED = 'kelurahan_desa_combined'
    DESA_KELURAHAN_NORMALIZED = 'desa_kelurahan_normalized'
    
    def __init__(self, parquet_dir: str = Config.DEFAULT_PARQUET_DIR, province: Optional[str] = None) -> None:
        """
        Initialize the ParquetJoiner with directory paths and logging setup.

        Sets up the parquet directory (absolute or relative to project root), log directory, and initializes the log file with CSV headers.
        The log file contains unmatched records in CSV format: province,kabupaten_kota,kecamatan,kode_kelurahan,kelurahan_desa,kodepos,source

        Args:
            parquet_dir (str): Base directory containing province subdirectories with parquet files. If relative, resolved from project root.
            province (Optional[str]): Specific province name for log file naming. If None, uses default log file.
        """
        script_dir: Path = Path(__file__).parent
        project_root: Path = script_dir.parent.parent
        if Path(parquet_dir).is_absolute():
            self.parquet_dir: Path = Path(parquet_dir)
        else:
            self.parquet_dir: Path = project_root / parquet_dir
        self.log_dir: Path = project_root / Config.LOG_DIR
        self.log_dir.mkdir(exist_ok=True)
        self.log_file: Path = self.log_dir / (f"{province}{Config.LOG_SUFFIX}" if province else Config.DEFAULT_LOG_FILE)
        self.lock: threading.Lock = threading.Lock()

        with open(self.log_file, 'w', encoding='utf-8') as f:
            f.write(f"province,{ParquetJoiner.KABUPATEN_KOTA},{ParquetJoiner.KECAMATAN},{ParquetJoiner.KODE_KELURAHAN},kelurahan_desa,{ParquetJoiner.KODEPOS},source\n")
    
    def join_province(self, province: str) -> StatsDict:
        """
        Join detail and pos files for a single province.

        Performs the complete join process: loads files, prepares data through normalization and filtering,
        executes left join, logs unmatched records, saves output, and generates statistics.

        Args:
            province (str): Province name (e.g., 'aceh') used to locate files and name outputs.

        Returns:
            StatsDict: Dictionary containing join statistics including counts, match rates, and file paths.

        Example:
            joiner = ParquetJoiner()
            stats = joiner.join_province('aceh')
            print(f"Matched {stats['matched_records']} records")
        """
        detail_file: Path = self.parquet_dir / province / f"{province}{ParquetJoiner.DETAIL_SUFFIX}"
        pos_file: Path = self.parquet_dir / province / f"{province}{ParquetJoiner.POS_SUFFIX}"
        output_file: Path = self.parquet_dir / province / f"{province}{ParquetJoiner.OUTPUT_SUFFIX}"

        # Check if files exist
        if not detail_file.exists():
            print(f"WARNING: Detail file not found: {detail_file}")
            return {"status": "skipped", "reason": "detail_file_missing"}

        if not pos_file.exists():
            print(f"WARNING: Pos file not found: {pos_file}")
            return {"status": "skipped", "reason": "pos_file_missing"}

        print(f"\n{'='*80}")
        print(f"Processing: {province}")
        print(f"{'='*80}")

        # Read files lazily
        df_detail: LazyFrame = pl.scan_parquet(detail_file)
        df_pos: LazyFrame = pl.scan_parquet(pos_file)
        
        print(f"Detail records: {df_detail.select(pl.len()).collect().item():,}")
        print(f"Pos records: {df_pos.select(pl.len()).collect().item():,}")

        # Prepare detail dataframe
        df_detail_complete: LazyFrame = self._prepare_detail_data(df_detail)
        print(f"Detail records with complete hierarchy: {df_detail_complete.select(pl.len()).collect().item():,}")

        # Prepare pos dataframe
        df_pos_prepared: LazyFrame = self._prepare_pos_data(df_pos)

        # Perform left join
        df_joined: LazyFrame = self._perform_join(df_detail_complete, df_pos_prepared)

        # Note: Keep normalized columns for logging, will drop before saving

        # Identify matched and unmatched records
        matched: LazyFrame = df_joined.filter(pl.col(ParquetJoiner.KODEPOS).is_not_null())
        unmatched_detail: LazyFrame = df_joined.filter(pl.col(ParquetJoiner.KODEPOS).is_null())

        # Identify unmapped pos records (anti-join)
        # These are pos records that don't match any detail record
        unmapped_pos: LazyFrame = df_pos_prepared.join(
            df_detail_complete.select([ParquetJoiner.KABUPATEN_KOTA, ParquetJoiner.KECAMATAN_NORMALIZED, ParquetJoiner.KELURAHAN_DESA_COMBINED]),
            left_on=[ParquetJoiner.KABUPATEN_KOTA_SOURCE, ParquetJoiner.KECAMATAN_NORMALIZED, ParquetJoiner.DESA_KELURAHAN_NORMALIZED],
            right_on=[ParquetJoiner.KABUPATEN_KOTA, ParquetJoiner.KECAMATAN_NORMALIZED, ParquetJoiner.KELURAHAN_DESA_COMBINED],
            how='anti'
        )

        # Log unmatched records
        unmatched_detail_collected: DataFrame = unmatched_detail.collect()
        unmapped_pos_collected: DataFrame = unmapped_pos.collect()
        self._log_unmatched_detail(province, unmatched_detail_collected)
        self._log_unmapped_pos(province, unmapped_pos_collected)

        # Drop normalized helper columns before saving
        df_output: LazyFrame = df_joined.drop([ParquetJoiner.KECAMATAN_NORMALIZED, ParquetJoiner.KELURAHAN_NORMALIZED, ParquetJoiner.DESA_NORMALIZED, ParquetJoiner.KELURAHAN_DESA_COMBINED])

        # Save joined data
        df_output.collect().write_parquet(str(output_file), compression=Config.COMPRESSION, row_group_size=Config.ROW_GROUP_SIZE)

        # Generate statistics
        stats: StatsDict = self._generate_statistics(province, df_detail, df_pos, matched, unmatched_detail, unmapped_pos, output_file)

        return stats
    
    def _log_unmatched_detail(self, province: str, unmatched: DataFrame) -> None:
        """Log detail records that don't have postal codes to CSV."""
        if len(unmatched) == 0:
            return

        with self.lock:
            with open(self.log_file, 'a', encoding='utf-8') as f:
                for row in unmatched.select([
                    ParquetJoiner.KABUPATEN_KOTA, ParquetJoiner.KECAMATAN, ParquetJoiner.KELURAHAN, ParquetJoiner.DESA, ParquetJoiner.KODE_KELURAHAN,
                    ParquetJoiner.KELURAHAN_NORMALIZED, ParquetJoiner.DESA_NORMALIZED
                ]).iter_rows(named=True):
                    kelurahan_desa_normalized = (row['kelurahan_normalized'] or '') + (row['desa_normalized'] or '')

                    f.write(f"{province},{row[ParquetJoiner.KABUPATEN_KOTA]},{row[ParquetJoiner.KECAMATAN]},{row[ParquetJoiner.KODE_KELURAHAN]},{kelurahan_desa_normalized},,detail\n")
    
    def _log_unmapped_pos(self, province: str, unmapped: DataFrame) -> None:
        """Log pos records that don't match any detail record to CSV."""
        if len(unmapped) == 0:
            return

        with self.lock:
            with open(self.log_file, 'a', encoding='utf-8') as f:
                for row in unmapped.select([
                    ParquetJoiner.KABUPATEN_KOTA_SOURCE, ParquetJoiner.KECAMATAN, ParquetJoiner.DESA_KELURAHAN, ParquetJoiner.KODEPOS,
                    ParquetJoiner.DESA_KELURAHAN_NORMALIZED
                ]).iter_rows(named=True):
                    kelurahan_desa_normalized = row['desa_kelurahan_normalized'] or ''

                    f.write(f"{province},{row[ParquetJoiner.KABUPATEN_KOTA_SOURCE]},{row[ParquetJoiner.KECAMATAN]},,{kelurahan_desa_normalized},{row[ParquetJoiner.KODEPOS]},pos\n")

    def _prepare_detail_data(self, df_detail: pl.LazyFrame) -> pl.LazyFrame:
        """
        Prepare detail dataframe by filtering and normalizing.

        Args:
            df_detail: Raw detail dataframe

        Returns:
            Prepared detail dataframe with complete hierarchy
        """
        df_detail_filtered: LazyFrame = df_detail.filter(
            (pl.col(ParquetJoiner.KODE_KELURAHAN).is_not_null()) &
            (pl.col(ParquetJoiner.KODE_KELURAHAN) != '')
        )

        print(f"Detail records after kode_kelurahan filter: {df_detail_filtered.select(pl.len()).collect().item():,}")

        df_detail_filtered = df_detail_filtered.with_columns([
            pl.col(ParquetJoiner.KELURAHAN).fill_null("").str.replace_all(r'\n|\r|\t', ' ').str.replace_all(r'\s+', ' ').str.strip_chars().str.replace_all(r'^\d+\s+', '').str.replace_all(r'^\d+\.\s*', '').str.replace_all(r'(?i)\bKel\.\s*', 'Kelurahan ').str.replace_all(r'(?i)\bDs\.\s*', 'Desa ').str.replace_all(r'(?i)\bKamp\.\s*', 'Kampung ').str.replace_all(r'(?i)\bDus\.\s*', 'Dusun ').alias(ParquetJoiner.KELURAHAN_NORMALIZED),
            pl.col(ParquetJoiner.DESA).fill_null("").str.replace_all(r'\n|\r|\t', ' ').str.replace_all(r'\s+', ' ').str.strip_chars().str.replace_all(r'^\d+\s+', '').str.replace_all(r'^\d+\.\s*', '').str.replace_all(r'(?i)\bKel\.\s*', 'Kelurahan ').str.replace_all(r'(?i)\bDs\.\s*', 'Desa ').str.replace_all(r'(?i)\bKamp\.\s*', 'Kampung ').str.replace_all(r'(?i)\bDus\.\s*', 'Dusun ').alias(ParquetJoiner.DESA_NORMALIZED),
            pl.col(ParquetJoiner.KECAMATAN).fill_null("").str.replace_all(r'\n|\r|\t', ' ').str.replace_all(r'\s+', ' ').str.strip_chars().str.replace_all(r'^\d+\.?\s+', '').str.replace_all(r'(?i)\bKec\.\s*', 'Kecamatan ').alias(ParquetJoiner.KECAMATAN_NORMALIZED)
        ])

        df_detail_filtered = df_detail_filtered.with_columns(
            (pl.col(ParquetJoiner.KELURAHAN_NORMALIZED) + pl.col(ParquetJoiner.DESA_NORMALIZED)).alias(ParquetJoiner.KELURAHAN_DESA_COMBINED)
        )

        df_detail_complete: LazyFrame = df_detail_filtered.filter(
            (pl.col(ParquetJoiner.KECAMATAN_NORMALIZED) != '') &
            (pl.col(ParquetJoiner.KELURAHAN_DESA_COMBINED) != '')
        )

        return df_detail_complete

    def _prepare_pos_data(self, df_pos: LazyFrame) -> LazyFrame:
        """
        Prepare pos dataframe by normalizing columns.

        Args:
            df_pos: Raw pos dataframe

        Returns:
            Prepared pos dataframe
        """
        df_pos_prepared: LazyFrame = df_pos.with_columns([
            pl.col(ParquetJoiner.KECAMATAN).fill_null("").str.replace_all(r'\n|\r|\t', ' ').str.replace_all(r'\s+', ' ').str.strip_chars().str.replace_all(r'^\d+\.?\s+', '').str.replace_all(r'(?i)\bKec\.\s*', 'Kecamatan ').alias(ParquetJoiner.KECAMATAN_NORMALIZED),
            pl.col(ParquetJoiner.DESA_KELURAHAN).fill_null("").str.replace_all(r'\n|\r|\t', ' ').str.replace_all(r'\s+', ' ').str.strip_chars().str.replace_all(r'^\d+\s+', '').str.replace_all(r'^\d+\.\s*', '').str.replace_all(r'(?i)\bKel\.\s*', 'Kelurahan ').str.replace_all(r'(?i)\bDs\.\s*', 'Desa ').str.replace_all(r'(?i)\bKamp\.\s*', 'Kampung ').str.replace_all(r'(?i)\bDus\.\s*', 'Dusun ').alias(ParquetJoiner.DESA_KELURAHAN_NORMALIZED)
        ])

        return df_pos_prepared

    def _perform_join(self, df_detail_complete: pl.LazyFrame, df_pos: pl.LazyFrame) -> pl.LazyFrame:
        """
        Perform left join between detail and pos dataframes.

        Args:
            df_detail_complete: Prepared detail dataframe
            df_pos: Prepared pos dataframe

        Returns:
            Joined dataframe
        """
        df_joined = df_detail_complete.join(
            df_pos.select([ParquetJoiner.KABUPATEN_KOTA_SOURCE, ParquetJoiner.KECAMATAN_NORMALIZED, ParquetJoiner.DESA_KELURAHAN_NORMALIZED, ParquetJoiner.KODEPOS]),
            left_on=[ParquetJoiner.KABUPATEN_KOTA, ParquetJoiner.KECAMATAN_NORMALIZED, ParquetJoiner.KELURAHAN_DESA_COMBINED],
            right_on=[ParquetJoiner.KABUPATEN_KOTA_SOURCE, ParquetJoiner.KECAMATAN_NORMALIZED, ParquetJoiner.DESA_KELURAHAN_NORMALIZED],
            how='left'
        )

        return df_joined

    def _generate_statistics(self, province: str, df_detail: LazyFrame, df_pos: LazyFrame, matched: LazyFrame, unmatched_detail: LazyFrame, unmapped_pos: LazyFrame, output_file: Path) -> StatsDict:
        """
        Generate statistics for the join operation.

        Args:
            province: Province name
            df_detail: Original detail dataframe
            df_pos: Original pos dataframe
            matched: Matched records dataframe
            unmatched_detail: Unmatched detail records dataframe
            unmapped_pos: Unmapped pos records dataframe
            output_file: Output file path

        Returns:
            Statistics dictionary
        """
        total_detail_count: int = df_detail.select(pl.len()).collect().item()
        total_pos_count: int = df_pos.select(pl.len()).collect().item()
        matched_count: int = matched.select(pl.len()).collect().item()
        unmatched_detail_count: int = unmatched_detail.select(pl.len()).collect().item()
        unmapped_pos_count: int = unmapped_pos.select(pl.len()).collect().item()
        stats: StatsDict = {
            "status": "success",
            "province": province,
            "total_detail_records": total_detail_count,
            "total_pos_records": total_pos_count,
            "matched_records": matched_count,
            "unmatched_detail_records": unmatched_detail_count,
            "unmapped_pos_records": unmapped_pos_count,
            "match_rate": f"{(matched_count / total_detail_count * 100):.2f}%",
            "output_file": output_file
        }

        print(f"\nStatistics:")
        print(f"  Matched (with kodepos): {stats['matched_records']:,} ({stats['match_rate']})")
        print(f"  Unmatched detail (no kodepos): {stats['unmatched_detail_records']:,}")
        print(f"  Unmapped pos (not in detail): {stats['unmapped_pos_records']:,}")
        print(f"  Output: {output_file}")
        print(f"  Log file: {self.log_file}")

        return stats

    def join_all_provinces(self) -> List[StatsDict]:
        """
        Join all provinces found in the parquet directory.

        Discovers province directories, processes them concurrently using ThreadPoolExecutor,
        collects statistics, and prints overall summary.

        Returns:
            List[StatsDict]: List of statistics dictionaries for each province processed.
        """
        province_dirs: List[Path] = [d for d in self.parquet_dir.iterdir() if d.is_dir()]
        provinces: List[str] = [d.name for d in province_dirs if not d.name.startswith('indonesia')]  # Skip merged file
        provinces.sort()

        print(f"\nFound {len(provinces)} provinces to process")

        all_stats: List[StatsDict] = []
        with concurrent.futures.ThreadPoolExecutor() as executor:
            futures: List[concurrent.futures.Future[StatsDict]] = [executor.submit(self.join_province, province) for province in provinces]
            all_stats = [f.result() for f in futures]

        print(f"\n{'='*80}")
        print("SUMMARY")
        print(f"{'='*80}")

        successful: List[StatsDict] = [s for s in all_stats if s.get('status') == 'success']
        skipped: List[StatsDict] = [s for s in all_stats if s.get('status') == 'skipped']
        
        print(f"Successfully processed: {len(successful)}")
        print(f"Skipped: {len(skipped)}")
        
        if successful:
            total_detail: int = sum(s['total_detail_records'] for s in successful)
            total_matched: int = sum(s['matched_records'] for s in successful)
            total_unmatched_detail: int = sum(s['unmatched_detail_records'] for s in successful)
            total_unmapped_pos: int = sum(s['unmapped_pos_records'] for s in successful)

            print(f"\nOverall Statistics:")
            print(f"  Total detail records: {total_detail:,}")
            print(f"  Matched (with kodepos): {total_matched:,} ({total_matched/total_detail*100:.2f}%)")
            print(f"  Unmatched detail: {total_unmatched_detail:,}")
            print(f"  Unmapped pos: {total_unmapped_pos:,}")

        print(f"\nDetailed log: {self.log_file}")

        return all_stats


def main() -> None:
    """
    Main entry point for the parquet join script.

    Parses command line arguments and executes join operations for specified province or all provinces.

    Examples:
        python join_parquet_files.py --province aceh
        python join_parquet_files.py --parquet-dir /custom/path
    """
    import argparse

    parser: argparse.ArgumentParser = argparse.ArgumentParser(description='Join detail and pos parquet files')
    parser.add_argument('--province', type=str, help='Specific province to process')
    parser.add_argument('--parquet-dir', type=str, default=Config.DEFAULT_PARQUET_DIR,
                         help=f'Base parquet directory (default: {Config.DEFAULT_PARQUET_DIR})')

    args: argparse.Namespace = parser.parse_args()

    if args.province:
        joiner: ParquetJoiner = ParquetJoiner(parquet_dir=args.parquet_dir, province=args.province)
        stats: StatsDict = joiner.join_province(args.province)
        if stats.get('status') == 'success':
            print(f"\nSuccessfully joined {args.province}")
        else:
            print(f"\nFailed to join {args.province}: {stats.get('reason')}")
    else:
        joiner: ParquetJoiner = ParquetJoiner(parquet_dir=args.parquet_dir)
        joiner.join_all_provinces()


if __name__ == "__main__":
    main()
