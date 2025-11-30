import json
import os
import time
from typing import Optional, Any

from ..batch_processor import BatchProcessor, _validate_kecamatan_data
from extractor.pdf_table_extractor import PDFTableExtractor
from utils.errors import BatchProcessingError, error_handler, log_error
from utils.paths import get_json_output_path, get_parquet_output_path, sanitize_folder_file_name
from utils.structure_utils import kecamatan_index_struct


def _extract_single_province_kecamatan(file_path: str, row: dict) -> tuple[dict, list[str]]:
    """Extract district data for a single province."""

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
        kecamatan_index, unmatched_names, unmapped_bsni = table_extractor.kecamatan_index(
            start_page=index_start, end_page=index_end, show_progress=False
        )

        extraction_time = time.time() - start_time
        result.update(
            {
                "success": True,
                "records": len(kecamatan_index),
                "time": extraction_time,
                "unmatched_names": unmatched_names,
                "unmapped_bsni": unmapped_bsni,
            }
        )

        # Save table data using Polars native methods
        folder_name_base = sanitize_folder_file_name(province_name)
        filename_base = sanitize_folder_file_name(index_name)
        path_base = os.path.join(folder_name_base, filename_base)
        json_debug_base = os.path.join(
            "debug", folder_name_base, filename_base
        )

        # Parquet (efficient storage)
        parquet_path = get_parquet_output_path(f"{path_base}.parquet", ensure_dir=True)
        kecamatan_index.write_parquet(parquet_path)
        log_messages.append(f"INFO: Saved Parquet for {province_name}: {parquet_path}")
        result["files"].append(parquet_path)

        # Validate extracted data
        validation_errors = _validate_kecamatan_data(kecamatan_index, province_name)

        # Debug JSON (metadata + sample data)
        debug_data = {
            "name": index_name,
            "page_range": {"start": index_start, "end": index_end},
            "table_format": index_table_format,
            "row_count": len(kecamatan_index),
            "columns": kecamatan_index.columns,
            "sample_data": kecamatan_index.head(3).to_dicts(),
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
        error_msg = f"Failed to extract kecamatan for {province_name}"
        log_error(BatchProcessingError(error_msg, province_name=province_name), "kecamatan_extraction")
        log_messages.append(f"ERROR: {error_msg}: {e}")

    return result, log_messages


@error_handler(operation_name="kecamatan_batch_processing", log_errors=True)
def execute_kecamatan_batch(config, logger=None) -> Optional[Any]:
    """Execute kecamatan index batch processing."""
    if logger is None:
        import logging
        logger = logging.getLogger(__name__)


    pdf_path = config.main_pdf
    structure_path = get_json_output_path("structure_pdf.json")

    if not os.path.exists(structure_path):
        raise BatchProcessingError("Structure file not found, run structure extraction first", file_path=structure_path)

    # Get all district index sections
    district_df = kecamatan_index_struct(structure_path, config.province_filter)
    if len(district_df) == 0:
        raise BatchProcessingError("No district index found in structure", file_path=structure_path)

    total_provinces = len(district_df)
    logger.info(f"Processing {total_provinces} provinces for kecamatan index")

    processor = BatchProcessor(config.max_workers)
    all_results = []

    # Process in batches
    for batch_start in range(0, total_provinces, config.batch_size):
        batch_df = district_df.slice(batch_start, config.batch_size)
        batch_end = min(batch_start + config.batch_size, total_provinces)

        logger.info(f"Processing batch {batch_start // config.batch_size + 1}: provinces {batch_start + 1}-{batch_end}")

        # Process batch
        if config.max_workers > 1:
            results = processor.process_batch(
                pdf_path, batch_df, _extract_single_province_kecamatan,
                item_name="province", log_filename=None
            )
        else:
            results = BatchProcessor.process_sequential(
                pdf_path, batch_df, _extract_single_province_kecamatan,
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

    # Collect and log unique unmatched ibukota_kabupaten_kota names with their kabupaten_kota
    all_unmatched = {}  # ibukota -> kabupaten_kota
    for result in successful:
        unmatched_names = result.get('unmatched_names', [])
        for ibukota, kabupaten_kota in unmatched_names:
            all_unmatched[ibukota] = kabupaten_kota

    if all_unmatched:
        log_path = os.path.join(os.path.dirname(__file__), "..", "..", "output", "log", "unmatched_k_bsni.log")

        # Ensure the log directory exists
        os.makedirs(os.path.dirname(log_path), exist_ok=True)

        # Write back the complete unique list
        with open(log_path, 'w', encoding='utf-8') as f:
            f.write(f"Batch processing completed - {len(all_unmatched)} unique unmatched ibukota_kabupaten_kota names across all provinces:\n")
            for name in sorted(all_unmatched.keys()):
                kabupaten = all_unmatched[name]
                f.write(f"  - {name} - {kabupaten}\n")
            f.write("\n")
        logger.info(f"Logged {len(all_unmatched)} unique unmatched ibukota_kabupaten_kota names with kabupaten_kota mapping")

    # Collect and log unmapped BSNI cities (BSNI entries not referenced by any district)
    all_unmapped_bsni = {}  # singkatan -> {nama_kota, kabupaten_kota, provinsi}
    for result in successful:
        unmapped_bsni = result.get('unmapped_bsni', [])
        for entry in unmapped_bsni:
            singkatan = entry.get('singkatan', '')
            if singkatan and singkatan not in all_unmapped_bsni:
                all_unmapped_bsni[singkatan] = entry

    if all_unmapped_bsni:
        log_path = os.path.join(os.path.dirname(__file__), "..", "..", "output", "log", "unmapped_bsni_cities.log")

        # Ensure the log directory exists
        os.makedirs(os.path.dirname(log_path), exist_ok=True)

        # Write unmapped BSNI cities
        with open(log_path, 'w', encoding='utf-8') as f:
            f.write(f"Batch processing completed - {len(all_unmapped_bsni)} BSNI cities not referenced by any district:\n")
            for singkatan in sorted(all_unmapped_bsni.keys()):
                entry = all_unmapped_bsni[singkatan]
                f.write(f"  - {singkatan}: {entry.get('nama_kota', '')} ({entry.get('kabupaten_kota', '')}, {entry.get('provinsi', '')})\n")
            f.write("\n")
        logger.info(f"Logged {len(all_unmapped_bsni)} unmapped BSNI cities")

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