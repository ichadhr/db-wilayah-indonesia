import json
import os
import time
import polars as pl
from typing import Dict, Optional, Any

from ..batch_processor import BatchProcessor
from extractor.pdf_table_extractor import PDFTableExtractor
from utils.paths import get_json_output_path, get_parquet_output_path, sanitize_folder_file_name
from utils.structure_utils import kabupaten_kota_detail_struct


def _extract_single_province_kabupaten_kota_detail(file_path: str, row: dict) -> tuple[Dict, list[str]]:
    """Extract detail data for a single kabupaten/kota."""
    from extractor.pdf_table_extractor import PDFTableExtractor

    province_name = row["province_name"]
    detail_name = row["name"]
    detail_table_format = row["table_format"]
    detail_start = row["start_page"]
    detail_end = row["end_page"]

    start_time = time.time()
    result = {
        "province_name": province_name,
        "detail_name": detail_name,
        "success": False,
        "records": None,
        "time": None,
        "error": None,
        "page_range": (detail_start, detail_end),
        "dataframe": None,
    }

    log_messages = []

    try:
        table_extractor = PDFTableExtractor(file_path)
        kabupaten_kota_detail = table_extractor.kabupaten_kota_detail(
            start_page=detail_start, end_page=detail_end, show_progress=False
        )

        extraction_time = time.time() - start_time
        result.update(
            {
                "success": True,
                "records": len(kabupaten_kota_detail),
                "time": extraction_time,
                "dataframe": kabupaten_kota_detail,
            }
        )

        log_messages.append(f"INFO: Extracted {len(kabupaten_kota_detail)} records for {detail_name}")

    except Exception as e:
        extraction_time = time.time() - start_time
        result.update({"time": extraction_time, "error": str(e)})
        log_messages.append(f"ERROR: Failed to extract detail for {detail_name}: {e}")

    return result, log_messages


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
    
    # Path for temporary combined file
    temp_parquet_path = get_parquet_output_path("temporary_kabupaten_kota_detail.parquet", ensure_dir=True)

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
        
        # Append successful batch results to temporary file
        successful_batch = [r for r in results if r["success"] and r.get("dataframe") is not None]
        if successful_batch:
            batch_dataframes = [r["dataframe"] for r in successful_batch]
            batch_combined = pl.concat(batch_dataframes, how="vertical")
            
            # Append to temporary file
            if os.path.exists(temp_parquet_path):
                existing_df = pl.read_parquet(temp_parquet_path)
                combined_df = pl.concat([existing_df, batch_combined], how="vertical")
                combined_df.write_parquet(temp_parquet_path)
            else:
                batch_combined.write_parquet(temp_parquet_path)
            
            logger.info(f"Appended {len(batch_combined)} records to temporary file")

    # Calculate summary
    successful = [r for r in all_results if r["success"]]
    failed = [r for r in all_results if not r["success"]]

    logger.info(f"Batch processing completed: {len(successful)} successful, {len(failed)} failed")

    if failed:
        for result in failed:
            logger.error(f"Failed detail {result['detail_name']}: {result['error']}")

    # Split temporary file by province
    files_generated = []
    if os.path.exists(temp_parquet_path):
        logger.info("Splitting temporary file by province...")
        all_data = pl.read_parquet(temp_parquet_path)
        
        # Get unique provinces
        provinces = all_data.select("provinsi").unique().to_series().to_list()
        
        for province_name in provinces:
            # Filter data for this province
            province_data = all_data.filter(pl.col("provinsi") == province_name)
            
            # Generate file paths with province folder
            folder_name_base = sanitize_folder_file_name(province_name)
            filename = f"{folder_name_base}_kabupaten_kota_detail"
            
            # Save Parquet in province folder
            parquet_path = get_parquet_output_path(os.path.join(folder_name_base, f"{filename}.parquet"), ensure_dir=True)
            province_data.write_parquet(parquet_path)
            files_generated.append(parquet_path)
            logger.info(f"Saved {province_name}: {parquet_path} ({len(province_data)} records)")
            
            # Save debug JSON in province folder
            province_results = [r for r in successful if r["province_name"] == province_name]
            debug_data = {
                "province_name": province_name,
                "total_records": len(province_data),
                "detail_count": len(province_results),
                "columns": province_data.columns,
                "sample_data": province_data.head(5).to_dicts(),
                "total_extraction_time_seconds": sum(r.get("time", 0.0) for r in province_results),
            }
            debug_path = get_json_output_path(os.path.join("debug", folder_name_base, f"{filename}.json"), ensure_dir=True)
            with open(debug_path, "w", encoding="utf-8") as f:
                json.dump(debug_data, f, ensure_ascii=False, indent=2)
            files_generated.append(debug_path)
        
        # Delete temporary file
        os.remove(temp_parquet_path)
        logger.info("Deleted temporary file")

    return type('Result', (), {
        'success': len(failed) == 0,
        'records_processed': sum(r.get('records', 0) for r in successful),
        'files_generated': files_generated,
        'metadata': {
            'total_details': total_details,
            'successful_details': len(successful),
            'failed_details': len(failed),
            'provinces_processed': len(files_generated) // 2  # Divide by 2 (parquet + json)
        },
        'error_message': f"{len(failed)} details failed" if failed else None
    })()
