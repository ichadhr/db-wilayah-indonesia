import json
import os
import time
from typing import Any, Optional

from extractor.pdf_table_extractor import PDFTableExtractor
from utils.errors import BatchProcessingError, error_handler, log_error
from utils.paths import (
    get_json_output_path,
    get_parquet_output_path,
    sanitize_folder_file_name,
)
from utils.structure_utils import kabupaten_kota_index_struct

from ..batch_processor import BatchProcessor, _validate_kabupaten_kota_data


def _extract_single_province_kabupaten_kota(
    file_path: str, row: dict
) -> tuple[dict, list[str]]:
    """Extract data for a single province (kabupaten/kota tables)."""

    province_name = row["province_name"]
    index_name = row["name"]
    index_table_format = row["table_format"]
    index_start = row["start_page"]
    index_end = row["end_page"]

    start_time = time.time()
    result = {
        "province_name": province_name,
        "success": False,
        "records": None,
        "time": None,
        "error": None,
        "page_range": (index_start, index_end),
        "files": [],
    }

    log_messages = []

    try:
        table_extractor = PDFTableExtractor(file_path)
        kabupaten_kota_index = table_extractor.kabupaten_kota_index(
            start_page=index_start, end_page=index_end, show_progress=False
        )

        extraction_time = time.time() - start_time
        result.update(
            {
                "success": True,
                "records": len(kabupaten_kota_index),
                "time": extraction_time,
            }
        )

        # Save table data using Polars native methods
        folder_name_base = sanitize_folder_file_name(province_name)
        filename_base = sanitize_folder_file_name(index_name)
        path_base = os.path.join(folder_name_base, filename_base)
        json_debug_base = os.path.join("debug", folder_name_base, filename_base)

        # Parquet (efficient storage)
        parquet_path = get_parquet_output_path(f"{path_base}.parquet", ensure_dir=True)
        kabupaten_kota_index.write_parquet(parquet_path)
        log_messages.append(f"INFO: Saved Parquet for {province_name}: {parquet_path}")
        result["files"].append(parquet_path)

        # Validate extracted data
        validation_errors = _validate_kabupaten_kota_data(
            kabupaten_kota_index, province_name
        )

        # Debug JSON (metadata + sample data)
        debug_data = {
            "name": index_name,
            "page_range": {"start": index_start, "end": index_end},
            "table_format": index_table_format,
            "row_count": len(kabupaten_kota_index),
            "columns": kabupaten_kota_index.columns,
            "sample_data": kabupaten_kota_index.head(3).to_dicts(),
            "extraction_time_seconds": extraction_time,
            "validation_errors": validation_errors,
        }
        debug_path = get_json_output_path(f"{json_debug_base}.json", ensure_dir=True)
        with open(debug_path, "w", encoding="utf-8") as f:
            json.dump(debug_data, f, ensure_ascii=False, indent=2)
        log_messages.append(f"INFO: Saved debug JSON for {province_name}: {debug_path}")
        result["files"].append(debug_path)

    except Exception as e:
        extraction_time = time.time() - start_time
        result.update({"time": extraction_time, "error": str(e)})
        error_msg = f"Failed to extract kabupaten/kota for {province_name}"
        log_error(
            BatchProcessingError(error_msg, province_name=province_name),
            "kabupaten_kota_extraction",
        )
        log_messages.append(f"ERROR: {error_msg}: {e}")

    return result, log_messages


@error_handler(operation_name="kabupaten_kota_batch_processing", log_errors=True)
def execute_kabupaten_kota_batch(config, logger=None) -> Optional[Any]:
    """Execute kabupaten/kota index batch processing."""
    if logger is None:
        import logging

        logger = logging.getLogger(__name__)

    pdf_path = config.main_pdf
    structure_path = get_json_output_path("structure_pdf.json")

    if not os.path.exists(structure_path):
        raise BatchProcessingError(
            "Structure file not found, run structure extraction first",
            file_path=structure_path,
        )

    # Get all regency index sections
    district_city_df = kabupaten_kota_index_struct(
        structure_path, config.province_filter
    )
    if len(district_city_df) == 0:
        raise BatchProcessingError(
            "No regency index found in structure", file_path=structure_path
        )

    total_provinces = len(district_city_df)
    logger.info(f"Processing {total_provinces} provinces for kabupaten/kota index")

    processor = BatchProcessor(config.max_workers)
    all_results = []

    # Process in batches
    for batch_start in range(0, total_provinces, config.batch_size):
        batch_df = district_city_df.slice(batch_start, config.batch_size)
        batch_end = min(batch_start + config.batch_size, total_provinces)

        logger.info(
            f"Processing batch {batch_start // config.batch_size + 1}: provinces {batch_start + 1}-{batch_end}"
        )

        # Process batch
        if config.max_workers > 1:
            results = processor.process_batch(
                pdf_path,
                batch_df,
                _extract_single_province_kabupaten_kota,
                item_name="province",
                log_filename=None,
            )
        else:
            results = BatchProcessor.process_sequential(
                pdf_path,
                batch_df,
                _extract_single_province_kabupaten_kota,
                item_name="province",
                log_filename=None,
            )

        all_results.extend(results)

    # Calculate summary
    successful = [r for r in all_results if r["success"]]
    failed = [r for r in all_results if not r["success"]]

    logger.info(
        f"Batch processing completed: {len(successful)} successful, {len(failed)} failed"
    )

    if failed:
        for result in failed:
            logger.error(
                f"Failed province {result['province_name']}: {result['error']}"
            )

    return type(
        "Result",
        (),
        {
            "success": len(failed) == 0,
            "records_processed": sum(r.get("records", 0) for r in successful),
            "files_generated": [f for r in successful for f in r.get("files", [])],
            "metadata": {
                "total_provinces": total_provinces,
                "successful_provinces": len(successful),
                "failed_provinces": len(failed),
            },
            "error_message": f"{len(failed)} provinces failed" if failed else None,
        },
    )()
