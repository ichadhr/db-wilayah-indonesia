import os
from typing import Optional, Any

from batch_processor import BatchProcessor, _extract_single_province_kabupaten_kota_detail
from utils.paths import get_json_output_path
from utils.structure_utils import kabupaten_kota_detail_struct


def execute_kabupaten_kota_detail_batch(config, logger=None) -> Optional[Any]:
    """Execute kabupaten/kota detail batch processing."""
    if logger is None:
        import logging
        logger = logging.getLogger(__name__)

    pdf_path = config.main_pdf
    structure_path = get_json_output_path("structure_pdf.json")

    if not os.path.exists(structure_path):
        raise ValueError("Structure file not found, run structure extraction first")

    # Get all regency detail sections
    detail_df = kabupaten_kota_detail_struct(structure_path, config.province_filter)
    if len(detail_df) == 0:
        raise ValueError("No kabupaten/kota detail found in structure")

    total_details = len(detail_df)
    logger.info(f"Processing {total_details} kabupaten/kota details")

    processor = BatchProcessor(config.max_workers)
    all_results = []

    # Process in batches
    for batch_start in range(0, total_details, config.batch_size):
        batch_end = min(batch_start + config.batch_size, total_details)
        batch_df = detail_df.slice(batch_start, batch_end)

        logger.info(f"Processing batch {batch_start // config.batch_size + 1}: details {batch_start + 1}-{batch_end}")

        # Process batch
        if config.max_workers > 1:
            results = processor.process_batch(
                pdf_path, batch_df, _extract_single_province_kabupaten_kota_detail,
                item_name="detail", log_filename=None
            )
        else:
            results = BatchProcessor.process_sequential(
                pdf_path, batch_df, _extract_single_province_kabupaten_kota_detail,
                item_name="detail", log_filename=None
            )

        all_results.extend(results)

    # Calculate summary
    successful = [r for r in all_results if r["success"]]
    failed = [r for r in all_results if not r["success"]]

    logger.info(f"Batch processing completed: {len(successful)} successful, {len(failed)} failed")

    if failed:
        for result in failed:
            logger.error(f"Failed detail {result['detail_name']}: {result['error']}")

    return type('Result', (), {
        'success': len(failed) == 0,
        'records_processed': sum(r.get('records', 0) for r in successful),
        'files_generated': [f for r in successful for f in r.get('files', [])],
        'metadata': {
            'total_details': total_details,
            'successful_details': len(successful),
            'failed_details': len(failed)
        },
        'error_message': f"{len(failed)} details failed" if failed else None
    })()