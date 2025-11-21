"""
Parquet File Merger Module
Utility for merging province-specific parquet files into consolidated datasets
"""

import os
import polars as pl
from pathlib import Path
from typing import Optional
import logging

from utils.paths import get_parquet_output_path
from utils.errors import error_handler, FileOperationError

logger = logging.getLogger(__name__)


class ParquetFileMerger:
    """Utility for merging parquet files from different provinces."""
    
    @staticmethod
    @error_handler(operation_name="merge_parquet_files", log_errors=True)
    def merge_province_parquet_files(
        parquet_dir: str,
        filename_pattern: str,
        output_filename: str,
        province_column_name: str = "provinsi"
    ) -> str:
        """
        Generic method to merge parquet files from province subdirectories.
        
        Args:
            parquet_dir: Base directory containing province folders
            filename_pattern: Glob pattern to match files (e.g., '*_kabupaten_kota_index.parquet')
            output_filename: Name for merged output file (without extension)
            province_column_name: Column name for province identifier (default: 'provinsi')
            
        Returns:
            Path to merged parquet file
            
        Raises:
            FileOperationError: If no parquet files found or merge fails
        """
        base_path = Path(parquet_dir)
        all_dataframes = []
        files_processed = 0
        files_failed = 0
        
        logger.info(f"Starting parquet merge: {filename_pattern}")
        logger.info(f"Searching in: {base_path}")
        
        # Find all province directories
        for province_dir in sorted(base_path.iterdir()):
            if not province_dir.is_dir():
                continue
                
            province_name = province_dir.name
            
            # Look for matching parquet files
            for parquet_file in province_dir.glob(filename_pattern):
                try:
                    logger.debug(f"Reading: {parquet_file}")
                    df = pl.read_parquet(parquet_file)
                    
                    # Add province column only if it doesn't already exist
                    if province_column_name not in df.columns:
                        df = df.with_columns(pl.lit(province_name).alias(province_column_name))
                        logger.debug(f"Added '{province_column_name}' column for {province_name}")
                    else:
                        logger.debug(f"'{province_column_name}' column already exists in {province_name}")
                    
                    all_dataframes.append(df)
                    files_processed += 1
                    logger.debug(f"[OK] Processed {province_name}: {len(df)} records")
                    
                except Exception as e:
                    files_failed += 1
                    logger.warning(f"[FAILED] Failed to read {parquet_file}: {e}")
                    continue
        
        if not all_dataframes:
            error_msg = f"No parquet files found matching pattern: {filename_pattern}"
            logger.error(error_msg)
            raise FileOperationError(
                error_msg,
                file_path=str(base_path),
                operation="merge"
            )
        
        logger.info(f"Files processed: {files_processed}, failed: {files_failed}")
        
        # Merge all DataFrames
        logger.info("Concatenating dataframes...")
        merged_df = pl.concat(all_dataframes, how="vertical")
        total_records = len(merged_df)
        logger.info(f"Merged {files_processed} files into {total_records} records")
        
        # Delete existing file if present
        output_path = get_parquet_output_path(f"{output_filename}.parquet", ensure_dir=True)
        if os.path.exists(output_path):
            logger.info(f"Removing existing file: {output_path}")
            os.remove(output_path)
        
        # Save merged file
        logger.info(f"Writing merged file: {output_path}")
        merged_df.write_parquet(output_path)
        
        logger.info(f"[OK] Successfully created merged file: {output_path}")
        logger.info(f"  Total records: {total_records}")
        
        return output_path
    
    @staticmethod
    def merge_kabupaten_kota_index(parquet_dir: Optional[str] = None) -> str:
        """
        Convenience method for merging kabupaten/kota index files.
        
        Args:
            parquet_dir: Base parquet directory (default: auto-detected from paths.py)
            
        Returns:
            Path to merged file: indonesia_kabupaten_kota_index.parquet
        """
        from utils.paths import get_output_subdir
        
        if parquet_dir is None:
            parquet_dir = get_output_subdir("parquet")
        
        logger.info("=== Merging Kabupaten/Kota Index Files ===")
        return ParquetFileMerger.merge_province_parquet_files(
            parquet_dir=parquet_dir,
            filename_pattern="*_kabupaten_kota_index.parquet",
            output_filename="indonesia_kabupaten_kota_index",
            province_column_name="provinsi"
        )
    
    @staticmethod
    def merge_kecamatan_index(parquet_dir: Optional[str] = None) -> str:
        """
        Convenience method for merging kecamatan index files.
        
        Args:
            parquet_dir: Base parquet directory (default: auto-detected from paths.py)
            
        Returns:
            Path to merged file: indonesia_kecamatan_index.parquet
        """
        from utils.paths import get_output_subdir
        
        if parquet_dir is None:
            parquet_dir = get_output_subdir("parquet")
        
        logger.info("=== Merging Kecamatan Index Files ===")
        return ParquetFileMerger.merge_province_parquet_files(
            parquet_dir=parquet_dir,
            filename_pattern="*_kecamatan_index.parquet",
            output_filename="indonesia_kecamatan_index",
            province_column_name="provinsi"
        )
    
    @staticmethod
    def merge_kabupaten_kota_detail(parquet_dir: Optional[str] = None) -> str:
        """
        Convenience method for merging kabupaten/kota detail files.
        
        Args:
            parquet_dir: Base parquet directory (default: auto-detected from paths.py)
            
        Returns:
            Path to merged file: indonesia_kabupaten_kota_detail.parquet
        """
        from utils.paths import get_output_subdir
        
        if parquet_dir is None:
            parquet_dir = get_output_subdir("parquet")
        
        logger.info("=== Merging Kabupaten/Kota Detail Files ===")
        return ParquetFileMerger.merge_province_parquet_files(
            parquet_dir=parquet_dir,
            filename_pattern="*_kabupaten_kota_detail.parquet",
            output_filename="indonesia_kabupaten_kota_detail",
            province_column_name="provinsi"
        )
