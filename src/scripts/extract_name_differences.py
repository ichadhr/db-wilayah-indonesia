#!/usr/bin/env python3
"""
Extract naming differences between detail and pos files from join log CSV.

This script analyzes the parquet_join.csv to find:
1. Kecamatan name differences (same kabupaten, different kecamatan spelling)
2. Kelurahan/Desa name differences (same kabupaten+kecamatan, different kelurahan spelling)

Outputs:
- kecamatan_mapping_candidates.csv: Potential kecamatan name mappings
- kelurahan_mapping_candidates.csv: Potential kelurahan name mappings using fuzzy matching
"""

import os
import argparse
import polars as pl
from difflib import SequenceMatcher
from typing import List, Dict, Optional, TypedDict

class KecamatanMapping(TypedDict):
    kabupaten_kota: str
    kecamatan_pos: str
    kecamatan_detail: str
    similarity: float
    status: str

class KelurahanMapping(TypedDict):
    kabupaten_kota: str
    kecamatan_pos: str
    kecamatan_detail: str
    kelurahan_pos: str
    kelurahan_detail: str
    similarity: float
    status: str

class Config:
    """Configuration class for NameDifferenceAnalyzer settings."""

    def __init__(self, kecamatan_threshold: float = 0.7, kelurahan_low_threshold: float = 0.8, kelurahan_high_threshold: float = 0.9, output_dir: str = 'src/log'):
        # Similarity thresholds
        self.KECAMATAN_SIMILARITY_THRESHOLD = kecamatan_threshold
        self.KELURAHAN_SIMILARITY_THRESHOLD_LOW = kelurahan_low_threshold
        self.KELURAHAN_SIMILARITY_THRESHOLD_HIGH = kelurahan_high_threshold

        # File paths and patterns
        self.DEFAULT_LOG_FILE = 'log/aceh_parquet_join.csv'
        self.OUTPUT_DIR = output_dir
        self.KECAMATAN_OUTPUT_PATTERN = '{province}_kecamatan_mapping_candidates.csv'
        self.KELURAHAN_OUTPUT_PATTERN = '{province}_kelurahan_mapping_candidates.csv'
        self.DEFAULT_KECAMATAN_OUTPUT = 'kecamatan_mapping_candidates.csv'
        self.DEFAULT_KELURAHAN_OUTPUT = 'kelurahan_mapping_candidates.csv'

class NameDifferenceAnalyzer:
    """Class to analyze naming differences between detail and pos files from join log CSV."""

    def __init__(self, log_file: Optional[str] = None, kecamatan_threshold: float = 0.7, kelurahan_low_threshold: float = 0.8, kelurahan_high_threshold: float = 0.9, output_dir: str = 'src/log') -> None:
        """Initialize the analyzer with the log file path and configuration parameters."""
        self.config: Config = Config(kecamatan_threshold, kelurahan_low_threshold, kelurahan_high_threshold, output_dir)
        self.log_file: str = log_file or self.config.DEFAULT_LOG_FILE
        self.df: pl.DataFrame

        # Check if log file exists
        if not os.path.exists(self.log_file):
            raise FileNotFoundError(f"Log file not found: {self.log_file}")

        self._load_data()

    def _load_data(self) -> None:
        """Load the log CSV data."""
        try:
            self.df = pl.read_csv(self.log_file)
        except Exception as e:
            raise RuntimeError(f"Failed to read CSV file '{self.log_file}': {e}")

        # Validate required columns
        required_columns = ['source', 'kabupaten_kota', 'kecamatan', 'kelurahan_desa']
        missing_columns = [col for col in required_columns if col not in self.df.columns]
        if missing_columns:
            raise ValueError(f"Missing required columns in '{self.log_file}': {missing_columns}")

    @staticmethod
    def similarity_ratio(a: str, b: str) -> float:
        """Calculate similarity ratio between two strings (0.0 to 1.0)."""
        return SequenceMatcher(None, a.lower(), b.lower()).ratio()

    def find_kecamatan_differences(self) -> List[KecamatanMapping]:
        """Find kecamatan name differences between detail and pos."""

        print("="*80)
        print("ANALYZING KECAMATAN NAME DIFFERENCES")
        print("="*80)

        # Use the loaded data
        df = self.df

        # Determine output filename based on input
        log_filename = os.path.basename(self.log_file)
        if log_filename.endswith('_parquet_join.csv') and log_filename != 'parquet_join.csv':
            province = log_filename[:-len('_parquet_join.csv')]
            kec_output = os.path.join(self.config.OUTPUT_DIR, self.config.KECAMATAN_OUTPUT_PATTERN.format(province=province))
        else:
            kec_output = os.path.join(self.config.OUTPUT_DIR, self.config.DEFAULT_KECAMATAN_OUTPUT)

        # Separate detail and pos records
        detail_df: pl.DataFrame = df.filter(pl.col('source') == 'detail')
        pos_df: pl.DataFrame = df.filter(pl.col('source') == 'pos')

        # Group by kabupaten to find kecamatan differences
        kecamatan_mapping: List[KecamatanMapping] = []

        # Get unique kabupaten
        kabupaten_list: List[str] = df['kabupaten_kota'].unique().to_list()

        for kabupaten in kabupaten_list:
            # Get kecamatan from detail and pos for this kabupaten
            detail_kec: List[str] = detail_df.filter(pl.col('kabupaten_kota') == kabupaten)['kecamatan'].unique().to_list()
            pos_kec: List[str] = pos_df.filter(pl.col('kabupaten_kota') == kabupaten)['kecamatan'].unique().to_list()

            # Find kecamatan in pos that don't exist in detail
            pos_only: set[str] = set(pos_kec) - set(detail_kec)

            if pos_only:
                print(f"\n{kabupaten}:")
                print(f"  Kecamatan in POS but not in DETAIL: {len(pos_only)}")

                # Try to find similar names in detail
                for pos_name in pos_only:
                    best_match: Optional[str] = None
                    best_ratio: float = 0.0

                    for detail_name in detail_kec:
                        ratio: float = self.similarity_ratio(pos_name, detail_name)
                        if ratio > best_ratio:
                            best_ratio = ratio
                            best_match = detail_name

                    # If similarity > threshold, it's likely a spelling variation
                    if best_match and best_ratio > self.config.KECAMATAN_SIMILARITY_THRESHOLD:
                        print(f"    {pos_name} -> {best_match} (similarity: {best_ratio:.2f})")
                        kecamatan_mapping.append({
                            'kabupaten_kota': kabupaten,
                            'kecamatan_pos': pos_name,
                            'kecamatan_detail': best_match,
                            'similarity': best_ratio,
                            'status': 'auto_matched'
                        })
                    else:
                        print(f"    {pos_name} -> NO MATCH (best: {best_match}, {best_ratio:.2f})")
                        kecamatan_mapping.append({
                            'kabupaten_kota': kabupaten,
                            'kecamatan_pos': pos_name,
                            'kecamatan_detail': best_match or '',
                            'similarity': best_ratio,
                            'status': 'needs_review'
                        })

        # Save to CSV
        if kecamatan_mapping:
            df_mapping: pl.DataFrame = pl.DataFrame(kecamatan_mapping)
            output_file: str = kec_output
            os.makedirs(os.path.dirname(output_file), exist_ok=True)
            try:
                df_mapping.write_csv(output_file)
                print(f"\n{'='*80}")
                print(f"Saved {len(kecamatan_mapping)} kecamatan mapping candidates to:")
                print(f"  {output_file}")
                print(f"\nAuto-matched (similarity > 0.7): {len([m for m in kecamatan_mapping if m['status'] == 'auto_matched'])}")
                print(f"Needs review: {len([m for m in kecamatan_mapping if m['status'] == 'needs_review'])}")
            except Exception as e:
                print(f"Error: Failed to save kecamatan mapping to '{output_file}': {e}")

        return kecamatan_mapping

    def find_kelurahan_differences(self) -> List[KelurahanMapping]:
            """Find kelurahan/desa name differences using fuzzy matching."""

            print("\n" + "="*80)
            print("ANALYZING KELURAHAN/DESA NAME DIFFERENCES")
            print("="*80)

            # Use the loaded data
            df: pl.DataFrame = self.df
    
            # Determine output filename based on input
            log_filename = os.path.basename(self.log_file)
            if log_filename.endswith('_parquet_join.csv') and log_filename != 'parquet_join.csv':
                province = log_filename[:-len('_parquet_join.csv')]
                kel_output = os.path.join(self.config.OUTPUT_DIR, self.config.KELURAHAN_OUTPUT_PATTERN.format(province=province))
            else:
                kel_output = os.path.join(self.config.OUTPUT_DIR, self.config.DEFAULT_KELURAHAN_OUTPUT)
    
            # Separate detail and pos records
            detail_df: pl.DataFrame = df.filter(pl.col('source') == 'detail')
            pos_df: pl.DataFrame = df.filter(pl.col('source') == 'pos')

            kelurahan_mapping: List[KelurahanMapping] = []

            # Group by kabupaten + kecamatan
            kabupaten_kecamatan_pairs: List[Dict[str, str]] = df.select(['kabupaten_kota', 'kecamatan']).unique().to_dicts()
    
            print(f"\nAnalyzing {len(kabupaten_kecamatan_pairs)} kabupaten+kecamatan combinations...")
    
            for pair in kabupaten_kecamatan_pairs:
                kabupaten: str = pair['kabupaten_kota']
                kecamatan: str = pair['kecamatan']

                # Get kelurahan from detail and pos for this kabupaten+kecamatan
                detail_kel: List[str] = detail_df.filter(
                    (pl.col('kabupaten_kota') == kabupaten) &
                    (pl.col('kecamatan') == kecamatan)
                )['kelurahan_desa'].unique().to_list()

                pos_kel: List[str] = pos_df.filter(
                    (pl.col('kabupaten_kota') == kabupaten) &
                    (pl.col('kecamatan') == kecamatan)
                )['kelurahan_desa'].unique().to_list()

                # Find similar names
                for pos_name in pos_kel:
                    best_match: Optional[str] = None
                    best_ratio: float = 0.0
    
                    for detail_name in detail_kel:
                        ratio: float = self.similarity_ratio(pos_name, detail_name)
                        if ratio > best_ratio:
                            best_ratio = ratio
                            best_match = detail_name
    
                    # If similarity > threshold, it's likely a spelling variation
                    if best_match and best_ratio > self.config.KELURAHAN_SIMILARITY_THRESHOLD_LOW and best_ratio < 1.0:
                        kelurahan_mapping.append({
                            'kabupaten_kota': kabupaten,
                            'kecamatan_pos': kecamatan,
                            'kecamatan_detail': kecamatan,
                            'kelurahan_pos': pos_name,
                            'kelurahan_detail': best_match,
                            'similarity': best_ratio,
                            'status': 'auto_matched' if best_ratio > self.config.KELURAHAN_SIMILARITY_THRESHOLD_HIGH else 'needs_review'
                        })
    
            # Save to CSV
            if kelurahan_mapping:
                df_mapping: pl.DataFrame = pl.DataFrame(kelurahan_mapping)
                # Sort by similarity descending
                df_mapping = df_mapping.sort('similarity', descending=True)
                output_file: str = kel_output
                os.makedirs(os.path.dirname(output_file), exist_ok=True)
                try:
                    df_mapping.write_csv(output_file)
                    print(f"\nFound {len(kelurahan_mapping)} kelurahan/desa mapping candidates")
                    print(f"Saved to: {output_file}")
                    print(f"\nTop 10 candidates:")
                    for row in df_mapping.head(10).to_dicts():
                        print(f"  {row['kelurahan_pos']} -> {row['kelurahan_detail']} ({row['similarity']:.3f})")
                    print(f"\nAuto-matched (similarity > 0.9): {len([m for m in kelurahan_mapping if m['status'] == 'auto_matched'])}")
                    print(f"Needs review (0.8-0.9): {len([m for m in kelurahan_mapping if m['status'] == 'needs_review'])}")
                except Exception as e:
                    print(f"Error: Failed to save kelurahan mapping to '{output_file}': {e}")
    
            return kelurahan_mapping

def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Extract naming differences between detail and pos files from join log CSV.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
            Examples:
            python extract_name_differences.py
            python extract_name_differences.py --input log/bali_parquet_join.csv --output-dir output/
            python extract_name_differences.py --kecamatan-threshold 0.8 --kelurahan-low-threshold 0.85
        """
    )

    parser.add_argument(
        '--input', '-i',
        type=str,
        default='log/aceh_parquet_join.csv',
        help='Path to the input log CSV file (default: log/aceh_parquet_join.csv)'
    )

    parser.add_argument(
        '--kecamatan-threshold',
        type=float,
        default=0.7,
        help='Similarity threshold for kecamatan name matching (default: 0.7)'
    )

    parser.add_argument(
        '--kelurahan-low-threshold',
        type=float,
        default=0.8,
        help='Low similarity threshold for kelurahan name matching (default: 0.8)'
    )

    parser.add_argument(
        '--kelurahan-high-threshold',
        type=float,
        default=0.9,
        help='High similarity threshold for kelurahan name matching (default: 0.9)'
    )

    parser.add_argument(
        '--output-dir',
        type=str,
        default='src/log',
        help='Directory to save output CSV files (default: src/log)'
    )

    args = parser.parse_args()

    print("\nEXTRACTING NAME DIFFERENCES FROM JOIN LOG")
    print("="*80)
    print(f"Input file: {args.input}")
    print(f"Output directory: {args.output_dir}")
    print(f"Kecamatan threshold: {args.kecamatan_threshold}")
    print(f"Kelurahan thresholds: {args.kelurahan_low_threshold} - {args.kelurahan_high_threshold}")

    try:
        # Create analyzer instance
        analyzer: NameDifferenceAnalyzer = NameDifferenceAnalyzer(
            log_file=args.input,
            kecamatan_threshold=args.kecamatan_threshold,
            kelurahan_low_threshold=args.kelurahan_low_threshold,
            kelurahan_high_threshold=args.kelurahan_high_threshold,
            output_dir=args.output_dir
        )

        # Find kecamatan differences
        kecamatan_mapping: List[KecamatanMapping] = analyzer.find_kecamatan_differences()

        # Find kelurahan differences
        kelurahan_mapping: List[KelurahanMapping] = analyzer.find_kelurahan_differences()

        print("\n" + "="*80)
        print("SUMMARY")
        print("="*80)
        print(f"Kecamatan mapping candidates: {len(kecamatan_mapping)}")
        print(f"Kelurahan mapping candidates: {len(kelurahan_mapping)}")
        print(f"\nReview the CSV files in {args.output_dir}/ to verify mappings.")
        print(f"Then we can apply these mappings to improve the join results.")
    except Exception as e:
        print(f"Error: {e}")
        print("Script failed gracefully.")
        return

if __name__ == "__main__":
    main()
