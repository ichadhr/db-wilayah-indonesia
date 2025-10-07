"""
Batch Processing Module
Generic batch processing for PDF table extractions with multiprocessing support
"""

import json
import multiprocessing as mp
from datetime import datetime
import time
import os
from typing import Callable, Dict, List, Optional

from utils.paths import (
    get_csv_output_path,
    get_json_output_path,
    get_parquet_output_path,
    sanitize_folder_file_name
)
from utils.progress import progress_manager


class BatchProcessor:
    """Generic batch processor for table extractions using multiprocessing"""

    def __init__(self, max_workers: int = 7):
        self.max_workers = max_workers

    def process_batch(
            self,
            file_path: str,
            data_sections_df,
            extraction_func: Callable[[str, dict], tuple[Dict, List[str]]],
            item_name: str = "item",
            log_filename: Optional[str] = None
    ) -> List[Dict]:
        """Process items in parallel using multiprocessing"""
        # Convert Polars rows to pickleable dicts
        tasks = []
        for row in data_sections_df.iter_rows(named=True):
            tasks.append(
                {
                    "province_name": str(row["province_name"]),
                    "name": str(row["name"]),
                    "table_format": str(row["table_format"]),
                    "start_page": int(row["start_page"]),
                    "end_page": int(row["end_page"]),
                }
            )

        results = []
        all_log_messages = []

        with progress_manager.batch_processing_progress(
                total_items=len(tasks), item_name=item_name, description=f"Processing {item_name}s"
        ) as progress_ctx:

            with mp.Pool(processes=self.max_workers) as pool:
                # Submit all tasks and collect results
                futures = [
                    pool.apply_async(_multiprocessing_worker, (file_path, task, extraction_func))
                    for task in tasks
                ]
                for future in futures:
                    result, log_messages = future.get()
                    results.append(result)
                    all_log_messages.extend(log_messages)
                    progress_ctx.advance(1)

        # Write all collected log messages to file
        if log_filename:
            with open(log_filename, 'a', encoding='utf-8') as f:
                for message in all_log_messages:
                    # Parse level and message
                    if message.startswith('INFO: '):
                        level = 'INFO'
                        msg = message[6:]
                    elif message.startswith('ERROR: '):
                        level = 'ERROR'
                        msg = message[7:]
                    else:
                        level = 'INFO'
                        msg = message

                    # Write formatted log entry
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    f.write(f"{timestamp} - {level} - {msg}\n")

        _print_batch_summary(results, log_filename)
        return results

    @staticmethod
    def process_sequential(
        file_path: str,
        data_sections_df,
        extraction_func: Callable[[str, dict], tuple[Dict, List[str]]],
        item_name: str = "item",
        log_filename: Optional[str] = None
    ) -> List[Dict]:
        """Process items sequentially (for debugging/low resource environments)"""
        rows = list(data_sections_df.iter_rows(named=True))
        results = []
        all_log_messages = []

        with progress_manager.batch_processing_progress(
                total_items=len(rows), item_name=item_name, description=f"Processing {item_name}s"
        ) as progress_context:
            for row in rows:
                result, log_messages = extraction_func(file_path, row)
                results.append(result)
                all_log_messages.extend(log_messages)
                progress_context.advance(1)

        # Write all collected log messages to file
        if log_filename:
            with open(log_filename, 'a', encoding='utf-8') as f:
                for message in all_log_messages:
                    # Parse level and message
                    if message.startswith('INFO: '):
                        level = 'INFO'
                        msg = message[6:]
                    elif message.startswith('ERROR: '):
                        level = 'ERROR'
                        msg = message[7:]
                    else:
                        level = 'INFO'
                        msg = message

                    # Write formatted log entry
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    f.write(f"{timestamp} - {level} - {msg}\n")

        _print_batch_summary(results, log_filename)
        return results


def _multiprocessing_worker(
        file_path: str,
        task: dict,
        extraction_func: Callable[[str, dict], tuple[Dict, List[str]]]
) -> tuple[Dict, list[str]]:
    """Worker function for multiprocessing (module-level, can be pickled)."""
    return extraction_func(file_path, task)


def _print_batch_summary(results: List[Dict], log_filename: Optional[str] = None):
    """Print a summary of batch processing results."""
    successful = [r for r in results if r["success"]]
    failed = [r for r in results if not r["success"]]

    print(f"[OK] {len(successful)} provinces processed successfully")
    for result in successful:
        records = result["records"]
        time_taken = result["time"]
        province = result["province_name"]
        if records == 0:
            start, end = result["page_range"]
            print(f"  - {province}: found 0 records, range page {start}-{end}")
        else:
            print(f"  - {province}: {records} records in {time_taken:.2f}s")

    if failed:
        print(f"[ERROR] {len(failed)} provinces failed")
        for result in failed:
            province = result["province_name"]
            error = result["error"]
            print(f"  - {province}: {error}")

    if log_filename:
        print(f"\nDetailed logs saved to: {log_filename}")


# Specific extraction functions
def _extract_single_province_kabupaten_kota(file_path: str, row: dict) -> tuple[Dict, list[str]]:
    """Extract data for a single province (kabupaten/kota tables)."""
    from extractor.pdf_table import PDFTableExtractor

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
        json_debug_base = os.path.join(
            "debug", folder_name_base, filename_base
        )

        # CSV (tabular data)
        csv_path = get_csv_output_path(f"{path_base}.csv", ensure_dir=True)
        kabupaten_kota_index.write_csv(csv_path)
        log_messages.append(f"INFO: Saved CSV for {province_name}: {csv_path}")
        result["files"].append(csv_path)

        # Parquet (efficient storage)
        parquet_path = get_parquet_output_path(f"{path_base}.parquet", ensure_dir=True)
        kabupaten_kota_index.write_parquet(parquet_path)
        log_messages.append(f"INFO: Saved Parquet for {province_name}: {parquet_path}")
        result["files"].append(parquet_path)

        # JSON (DataFrame data only)
        json_path = get_json_output_path(f"{path_base}.json", ensure_dir=True)
        kabupaten_kota_index.write_json(json_path)
        log_messages.append(f"INFO: Saved JSON for {province_name}: {json_path}")
        result["files"].append(json_path)

        # Debug JSON (metadata + sample data)
        debug_data = {
            "name": index_name,
            "page_range": {"start": index_start, "end": index_end},
            "table_format": index_table_format,
            "row_count": len(kabupaten_kota_index),
            "columns": kabupaten_kota_index.columns,
            "sample_data": kabupaten_kota_index.head(3).to_dicts(),
            "extraction_time_seconds": extraction_time,
        }
        debug_path = get_json_output_path(f"{json_debug_base}.json", ensure_dir=True)
        with open(debug_path, "w", encoding="utf-8") as f:
            json.dump(debug_data, f, ensure_ascii=False, indent=2)
        log_messages.append(f"INFO: Saved debug JSON for {province_name}: {debug_path}")
        result["files"].append(debug_path)

    except Exception as e:
        extraction_time = time.time() - start_time
        result.update({"time": extraction_time, "error": str(e)})
        log_messages.append(f"ERROR: Failed to extract {province_name}: {e}")

    return result, log_messages


# Public API functions
def _extract_single_province_kecamatan(file_path: str, row: dict) -> tuple[Dict, list[str]]:
    """Extract district data for a single province."""
    from extractor.pdf_table import PDFTableExtractor

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
        kecamatan_index = table_extractor.kecamatan_index(
            start_page=index_start, end_page=index_end, show_progress=False
        )

        extraction_time = time.time() - start_time
        result.update(
            {
                "success": True,
                "records": len(kecamatan_index),
                "time": extraction_time,
            }
        )

        # Save table data using Polars native methods
        folder_name_base = sanitize_folder_file_name(province_name)
        filename_base = sanitize_folder_file_name(index_name)
        path_base = os.path.join(folder_name_base, filename_base)
        json_debug_base = os.path.join(
            "debug", folder_name_base, filename_base
        )

        # CSV (tabular data)
        csv_path = get_csv_output_path(f"{path_base}.csv", ensure_dir=True)
        kecamatan_index.write_csv(csv_path)
        log_messages.append(f"INFO: Saved CSV for {province_name}: {csv_path}")
        result["files"].append(csv_path)

        # Parquet (efficient storage)
        parquet_path = get_parquet_output_path(f"{path_base}.parquet", ensure_dir=True)
        kecamatan_index.write_parquet(parquet_path)
        log_messages.append(f"INFO: Saved Parquet for {province_name}: {parquet_path}")
        result["files"].append(parquet_path)

        # JSON (DataFrame data only)
        json_path = get_json_output_path(f"{path_base}.json", ensure_dir=True)
        kecamatan_index.write_json(json_path)
        log_messages.append(f"INFO: Saved JSON for {province_name}: {json_path}")
        result["files"].append(json_path)

        # Debug JSON (metadata + sample data)
        debug_data = {
            "name": index_name,
            "page_range": {"start": index_start, "end": index_end},
            "table_format": index_table_format,
            "row_count": len(kecamatan_index),
            "columns": kecamatan_index.columns,
            "sample_data": kecamatan_index.head(3).to_dicts(),
            "extraction_time_seconds": extraction_time,
        }
        debug_path = get_json_output_path(f"{json_debug_base}.json", ensure_dir=True)
        with open(debug_path, "w", encoding="utf-8") as f:
            json.dump(debug_data, f, ensure_ascii=False, indent=2)
        log_messages.append(f"INFO: Saved debug JSON for {province_name}: {debug_path}")
        result["files"].append(debug_path)

    except Exception as e:
        extraction_time = time.time() - start_time
        result.update({"time": extraction_time, "error": str(e)})
        log_messages.append(f"ERROR: Failed to extract kecamatan for {province_name}: {e}")

    return result, log_messages


# Public API functions

