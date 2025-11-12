import os
from typing import Optional, Any

from batch_processor import BatchProcessor, _extract_single_province_kabupaten_kota
from utils.paths import get_json_output_path
from utils.structure_utils import kabupaten_kota_index_struct


def execute_kabupaten_kota_batch(config, logger=None) -> Optional[Any]:
    """Execute kabupaten/kota index batch processing."""
    if logger is None:
        import logging
        logger = logging.getLogger(__name__)

    pdf_path = config.main_pdf
    structure_path = get_json_output_path("structure_pdf.json")

    if not os.path.exists(structure_path):
        raise ValueError("Structure file not found, run structure extraction first")

    # Get all regency index sections
    district_city_df = kabupaten_kota_index_struct(structure_path, config.province_filter)
    if len(district_city_df) == 0:
        raise ValueError("No regency index found in structure")

    total_provinces = len(district_city_df)
    logger.info(f"Processing {total_provinces} provinces for kabupaten/kota index")

    processor = BatchProcessor(config.max_workers)
    all_results = []

    # Process in batches
    for batch_start in range(0, total_provinces, config.batch_size):
        batch_end = min(batch_start + config.batch_size, total_provinces)
        batch_df = district_city_df.slice(batch_start, batch_end)

        logger.info(f"Processing batch {batch_start // config.batch_size + 1}: provinces {batch_start + 1}-{batch_end}")

        # Process batch
        if config.max_workers > 1:
            results = processor.process_batch(
                pdf_path, batch_df, _extract_single_province_kabupaten_kota,
                item_name="province", log_filename=None
            )
        else:
            results = BatchProcessor.process_sequential(
                pdf_path, batch_df, _extract_single_province_kabupaten_kota,
                item_name="province", log_filename=None
            )

        all_results.extend(results)

    # Calculate summary
    successful = [r for r in all_results if r["success"]]
    failed = [r for r in all_results if not r["success"]]

    logger.info(f"Batch processing completed: {len(successful)} successful, {len(failed)} failed")

    if failed:
        for result in failed:
            logger.error(f"Failed province {result['province_name']}: {result['error']}")

    return type('Result', (), {
        'success': len(failed) == 0,
        'records_processed': sum(r.get('records', 0) for r in successful),
        'files_generated': [f for r in successful for f in r.get('files', [])],
        'metadata': {
            'total_provinces': total_provinces,
            'successful_provinces': len(successful),
            'failed_provinces': len(failed)
        },
        'error_message': f"{len(failed)} provinces failed" if failed else None
    })()