"""
Parquet Merge Pipeline Step
Merges province-specific parquet files into consolidated datasets
"""

import logging
from typing import Any, Optional

from utils.data_merger import ParquetFileMerger
from utils.errors import error_handler

logger = logging.getLogger(__name__)


@error_handler(operation_name="parquet_merge_step", log_errors=True)
def execute_parquet_merge(logger=None) -> Optional[Any]:
    """
    Execute parquet file merging step.

    Merges all province-specific parquet files into consolidated datasets:
    - kabupaten/kota index files -> indonesia_kabupaten_kota_index.parquet
    - kecamatan index files -> indonesia_kecamatan_index.parquet
    - kabupaten/kota detail files -> indonesia_kabupaten_kota_detail.parquet

    Args:
        config: Pipeline configuration
        logger: Logger instance (optional)

    Returns:
        Result object with success status, files generated, and metadata
    """
    if logger is None:
        logger = logging.getLogger(__name__)

    files_generated = []
    total_records = 0

    try:
        logger.info("=" * 60)
        logger.info("Starting Parquet File Merge Process")
        logger.info("=" * 60)

        # Merge kabupaten/kota index
        logger.info("\n[1/3] Merging Kabupaten/Kota Index Files...")
        path = ParquetFileMerger.merge_kabupaten_kota_index()
        files_generated.append(path)
        logger.info(f"[OK] Created: {path}")

        # Merge kecamatan index
        logger.info("\n[2/3] Merging Kecamatan Index Files...")
        path = ParquetFileMerger.merge_kecamatan_index()
        files_generated.append(path)
        logger.info(f"[OK] Created: {path}")

        # Merge kabupaten/kota detail
        logger.info("\n[3/3] Merging Kabupaten/Kota Detail Files...")
        path = ParquetFileMerger.merge_kabupaten_kota_detail()
        files_generated.append(path)
        logger.info(f"[OK] Created: {path}")

        logger.info("\n" + "=" * 60)
        logger.info("Parquet Merge Completed Successfully")
        logger.info(f"Total merged files created: {len(files_generated)}")
        logger.info("=" * 60)

        return type(
            "Result",
            (),
            {
                "success": True,
                "records_processed": total_records,
                "files_generated": files_generated,
                "metadata": {
                    "merged_files": len(files_generated),
                    "output_files": files_generated,
                },
                "error_message": None,
            },
        )()

    except Exception as e:
        logger.error(f"Parquet merge failed: {e}")
        logger.error(f"Files created before failure: {files_generated}")
        return type(
            "Result",
            (),
            {
                "success": False,
                "records_processed": 0,
                "files_generated": files_generated,
                "metadata": {},
                "error_message": str(e),
            },
        )()
