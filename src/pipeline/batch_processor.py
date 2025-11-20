"""
Batch Processing Module
Generic batch processing for PDF table extractions with multiprocessing support
"""

import json
import multiprocessing as mp
from datetime import datetime
import time
import os
import logging
from typing import Any, Callable, Dict, List, Optional

from utils.paths import (
    get_csv_output_path,
    get_json_output_path,
    get_parquet_output_path,
    sanitize_folder_file_name
)
from utils.progress import progress_manager


# Global shutdown event for graceful termination
shutdown_event = mp.Event()


class BatchProcessor:
    """Generic batch processor for table extractions using multiprocessing"""

    def __init__(self, max_workers: int = 7):
        self.max_workers = max_workers
        self.logger = logging.getLogger(__name__)
        self.batch_stats = {
            'total_batches': 0,
            'successful_batches': 0,
            'failed_batches': 0,
            'total_processing_time': 0.0,
            'total_records': 0,
            'error_summary': {}
        }

    def process_batch(
            self,
            file_path: str,
            data_sections_df,
            extraction_func: Callable[[str, dict], tuple[Dict, List[str]]],
            item_name: str = "item",
            log_filename: Optional[str] = None
    ) -> List[Dict]:
        """Process items in parallel using multiprocessing with enhanced error handling"""
        batch_start_time = time.time()

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
        failed_tasks = []

        with progress_manager.batch_processing_progress(
                total_items=len(tasks), item_name=item_name, description=f"Processing {item_name}s"
        ) as progress_ctx:

            pool = None
            try:
                pool = mp.Pool(processes=self.max_workers)
                # Submit all tasks and collect results with timeout and error handling
                futures = [
                    pool.apply_async(_multiprocessing_worker, (file_path, task, extraction_func))
                    for task in tasks
                ]

                for i, future in enumerate(futures):
                    # Check for shutdown signal
                    if shutdown_event.is_set():
                        self.logger.warning("Shutdown signal detected, terminating remaining tasks...")
                        pool.terminate()
                        pool.join()

                        # Mark remaining tasks as cancelled
                        for j in range(i, len(tasks)):
                            province_name = tasks[j]["province_name"]
                            cancelled_result = {
                                "province_name": province_name,
                                "success": False,
                                "error": "Task cancelled due to shutdown",
                                "records": 0,
                                "time": 0.0,
                                "files": []
                            }
                            results.append(cancelled_result)
                            failed_tasks.append(province_name)
                            progress_ctx.advance(1)
                        break

                    try:
                        # Add timeout to prevent hanging
                        result, log_messages = future.get(timeout=300)  # 5 minute timeout
                        results.append(result)
                        all_log_messages.extend(log_messages)
                        progress_ctx.advance(1)
                    except mp.TimeoutError:
                        province_name = tasks[i]["province_name"]
                        error_msg = f"Timeout processing {province_name} after 5 minutes"
                        self.logger.error(error_msg)
                        failed_result = {
                            "province_name": province_name,
                            "success": False,
                            "error": error_msg,
                            "records": 0,
                            "time": 300.0,
                            "files": []
                        }
                        results.append(failed_result)
                        failed_tasks.append(province_name)
                        progress_ctx.advance(1)
                    except Exception as e:
                        province_name = tasks[i]["province_name"]
                        error_msg = f"Unexpected error processing {province_name}: {str(e)}"
                        self.logger.error(error_msg)
                        failed_result = {
                            "province_name": province_name,
                            "success": False,
                            "error": error_msg,
                            "records": 0,
                            "time": 0.0,
                            "files": []
                        }
                        results.append(failed_result)
                        failed_tasks.append(province_name)
                        progress_ctx.advance(1)

            except KeyboardInterrupt:
                # Handle KeyboardInterrupt gracefully
                self.logger.warning("KeyboardInterrupt detected, terminating pool...")
                shutdown_event.set()  # Ensure shutdown event is set
                if pool:
                    pool.terminate()
                    pool.join()
                # Mark remaining tasks as cancelled
                for task in tasks[len(results):]:
                    cancelled_result = {
                        "province_name": task["province_name"],
                        "success": False,
                        "error": "Task cancelled due to KeyboardInterrupt",
                        "records": 0,
                        "time": 0.0,
                        "files": []
                    }
                    results.append(cancelled_result)
                    failed_tasks.append(task["province_name"])
                    progress_ctx.advance(1)
                # Re-raise KeyboardInterrupt so orchestrator can handle it
                raise
            except Exception as pool_error:
                self.logger.error(f"Pool processing error: {pool_error}")
                # Mark remaining tasks as failed
                for task in tasks[len(results):]:
                    failed_result = {
                        "province_name": task["province_name"],
                        "success": False,
                        "error": f"Pool error: {str(pool_error)}",
                        "records": 0,
                        "time": 0.0,
                        "files": []
                    }
                    results.append(failed_result)
                    failed_tasks.append(task["province_name"])
                    progress_ctx.advance(1)
            finally:
                if pool:
                    pool.close()
                    pool.join()

        # Update batch statistics
        batch_time = time.time() - batch_start_time
        successful_results = [r for r in results if r.get("success", False)]
        failed_results = [r for r in results if not r.get("success", True)]

        self.batch_stats['total_batches'] += 1
        self.batch_stats['successful_batches'] += 1 if len(failed_results) == 0 else 0
        self.batch_stats['failed_batches'] += 1 if len(failed_results) > 0 else 0
        self.batch_stats['total_processing_time'] += batch_time
        self.batch_stats['total_records'] += sum(r.get("records", 0) for r in successful_results)

        # Collect error summary
        for result in failed_results:
            error = result.get("error", "Unknown error")
            if error in self.batch_stats['error_summary']:
                self.batch_stats['error_summary'][error] += 1
            else:
                self.batch_stats['error_summary'][error] = 1

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
        extraction_func: Callable[[Any, dict], tuple[Dict, List[str]]]
) -> tuple[Dict, list[str]]:
    """Worker function for multiprocessing (module-level, can be pickled)."""
    # Check shutdown event at the start of worker
    if shutdown_event.is_set():
        return {
            "province_name": task.get("province_name", "unknown"),
            "success": False,
            "error": "Task cancelled due to shutdown signal",
            "records": 0,
            "time": 0.0,
            "files": []
        }, []

    try:
        return extraction_func(file_path, task)
    except KeyboardInterrupt:
        # Handle KeyboardInterrupt gracefully in worker
        shutdown_event.set()  # Ensure shutdown event is set for other workers
        return {
            "province_name": task.get("province_name", "unknown"),
            "success": False,
            "error": "Task interrupted by KeyboardInterrupt",
            "records": 0,
            "time": 0.0,
            "files": []
        }, []
    except Exception as e:
         return {
            "province_name": task.get("province_name", "unknown"),
            "success": False,
            "error": f"Worker error: {str(e)}",
            "records": 0,
            "time": 0.0,
            "files": []
        }, []


def _print_batch_summary(results: List[Dict], log_filename: Optional[str] = None):
    """Print a summary of batch processing results."""
    successful = [r for r in results if r["success"]]
    failed = [r for r in results if not r["success"]]

    print(f"[OK] {len(successful)} provinces processed successfully")
    for result in successful:
        records = result["records"]
        time_taken = result["time"]
        province = result["province_name"]
        # Check if this is a detail extraction with specific name
        detail_name = result.get("detail_name")
        if detail_name:
            display_name = f"{province} - {detail_name}"
        else:
            display_name = province
        if records == 0:
            start, end = result["page_range"]
            print(f"  - {display_name}: found 0 records, range page {start}-{end}")
        else:
            print(f"  - {display_name}: {records} records in {time_taken:.2f}s")

    if failed:
        print(f"[ERROR] {len(failed)} provinces failed")
        for result in failed:
            province = result["province_name"]
            error = result["error"]
            print(f"  - {province}: {error}")

    if log_filename:
        print(f"\nDetailed logs saved to: {log_filename}")


    def get_batch_statistics(self) -> Dict:
        """Get current batch processing statistics."""
        return self.batch_stats.copy()


def _validate_kabupaten_kota_data(df, province_name: str) -> List[str]:
    """Validate kabupaten/kota index data for consistency and completeness."""
    errors = []

    if len(df) == 0:
        errors.append(f"No kabupaten/kota records found for {province_name}")
        return errors
    
    
    def _validate_kecamatan_data(df, province_name: str) -> List[str]:
        """Validate kecamatan index data for consistency and completeness."""
        errors = []
    
        if len(df) == 0:
            errors.append(f"No kecamatan records found for {province_name}")
            return errors
    
        # Check required columns
        required_columns = ["nama_kecamatan", "kode_kecamatan", "nama_kabupaten_kota", "kode_kabupaten_kota"]
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            errors.append(f"Missing required columns: {missing_columns}")
    
        # Check for empty/null values in critical fields
        for col in ["nama_kecamatan", "kode_kecamatan", "nama_kabupaten_kota", "kode_kabupaten_kota"]:
            if col in df.columns:
                null_count = df.filter(df[col].is_null() | (df[col] == "")).height
                if null_count > 0:
                    errors.append(f"Found {null_count} null/empty values in {col}")
    
        # Validate kecamatan codes (should be 6 digits)
        if "kode_kecamatan" in df.columns:
            invalid_codes = []
            for row in df.iter_rows(named=True):
                code = str(row.get("kode_kecamatan", ""))
                if code and (len(code) != 6 or not code.isdigit()):
                    invalid_codes.append(f"{row.get('nama_kecamatan', 'Unknown')}: {code}")
            if invalid_codes:
                errors.append(f"Invalid kecamatan codes: {invalid_codes[:3]}")  # Show first 3
    
        # Validate kabupaten/kota codes (should be 4 digits)
        if "kode_kabupaten_kota" in df.columns:
            invalid_codes = []
            for row in df.iter_rows(named=True):
                code = str(row.get("kode_kabupaten_kota", ""))
                if code and (len(code) != 4 or not code.isdigit()):
                    invalid_codes.append(f"{row.get('nama_kabupaten_kota', 'Unknown')}: {code}")
            if invalid_codes:
                errors.append(f"Invalid kabupaten/kota codes: {invalid_codes[:3]}")  # Show first 3
    
        # Check for duplicate kecamatan names within same kabupaten/kota
        if all(col in df.columns for col in ["nama_kecamatan", "nama_kabupaten_kota"]):
            grouped_duplicates = {}
            for row in df.iter_rows(named=True):
                key = (row.get("nama_kabupaten_kota", ""), row.get("nama_kecamatan", ""))
                if key in grouped_duplicates:
                    grouped_duplicates[key] += 1
                else:
                    grouped_duplicates[key] = 1
    
            duplicates = [f"{kab_kota}.{kec} ({count})" for (kab_kota, kec), count in grouped_duplicates.items() if count > 1]
            if duplicates:
                errors.append(f"Duplicate kecamatan names within kabupaten/kota: {duplicates[:3]}")
    
        return errors

    # Check required columns
    required_columns = ["nama_kabupaten_kota", "kode_kabupaten_kota"]
    missing_columns = [col for col in required_columns if col not in df.columns]
    if missing_columns:
        errors.append(f"Missing required columns: {missing_columns}")

    # Check for empty/null values in critical fields
    for col in ["nama_kabupaten_kota", "kode_kabupaten_kota"]:
        if col in df.columns:
            null_count = df.filter(df[col].is_null() | (df[col] == "")).height
            if null_count > 0:
                errors.append(f"Found {null_count} null/empty values in {col}")

    # Validate codes (should be 4 digits)
    if "kode_kabupaten_kota" in df.columns:
        invalid_codes = []
        for row in df.iter_rows(named=True):
            code = str(row.get("kode_kabupaten_kota", ""))
            if code and (len(code) != 4 or not code.isdigit()):
                invalid_codes.append(f"{row.get('nama_kabupaten_kota', 'Unknown')}: {code}")
        if invalid_codes:
            errors.append(f"Invalid kabupaten/kota codes: {invalid_codes[:3]}")  # Show first 3

    # Check for duplicate names or codes
    if "nama_kabupaten_kota" in df.columns:
        names = [row["nama_kabupaten_kota"] for row in df.iter_rows(named=True) if row.get("nama_kabupaten_kota")]
        if len(names) != len(set(names)):
            duplicates = [name for name in names if names.count(name) > 1]
            errors.append(f"Duplicate kabupaten/kota names: {list(set(duplicates))}")

    if "kode_kabupaten_kota" in df.columns:
        codes = [str(row["kode_kabupaten_kota"]) for row in df.iter_rows(named=True) if row.get("kode_kabupaten_kota")]
        if len(codes) != len(set(codes)):
            duplicates = [code for code in codes if codes.count(code) > 1]
            errors.append(f"Duplicate kabupaten/kota codes: {list(set(duplicates))}")

    return errors


def _validate_kecamatan_data(df, province_name: str) -> List[str]:
    """Validate kecamatan index data for consistency and completeness."""
    errors = []

    if len(df) == 0:
        errors.append(f"No kecamatan records found for {province_name}")
        return errors

    # Check required columns
    required_columns = ["nama_kecamatan", "kode_kecamatan", "nama_kabupaten_kota", "kode_kabupaten_kota"]
    missing_columns = [col for col in required_columns if col not in df.columns]
    if missing_columns:
        errors.append(f"Missing required columns: {missing_columns}")

    # Check for empty/null values in critical fields
    for col in ["nama_kecamatan", "kode_kecamatan", "nama_kabupaten_kota", "kode_kabupaten_kota"]:
        if col in df.columns:
            null_count = df.filter(df[col].is_null() | (df[col] == "")).height
            if null_count > 0:
                errors.append(f"Found {null_count} null/empty values in {col}")

    # Validate kecamatan codes (should be 6 digits)
    if "kode_kecamatan" in df.columns:
        invalid_codes = []
        for row in df.iter_rows(named=True):
            code = str(row.get("kode_kecamatan", ""))
            if code and (len(code) != 6 or not code.isdigit()):
                invalid_codes.append(f"{row.get('nama_kecamatan', 'Unknown')}: {code}")
        if invalid_codes:
            errors.append(f"Invalid kecamatan codes: {invalid_codes[:3]}")  # Show first 3

    # Validate kabupaten/kota codes (should be 4 digits)
    if "kode_kabupaten_kota" in df.columns:
        invalid_codes = []
        for row in df.iter_rows(named=True):
            code = str(row.get("kode_kabupaten_kota", ""))
            if code and (len(code) != 4 or not code.isdigit()):
                invalid_codes.append(f"{row.get('nama_kabupaten_kota', 'Unknown')}: {code}")
        if invalid_codes:
            errors.append(f"Invalid kabupaten/kota codes: {invalid_codes[:3]}")  # Show first 3

    # Check hierarchical relationships: kecamatan code should start with kabupaten/kota code
    if all(col in df.columns for col in ["kode_kecamatan", "kode_kabupaten_kota"]):
        invalid_hierarchy = []
        for row in df.iter_rows(named=True):
            kec_code = str(row.get("kode_kecamatan", ""))
            kab_code = str(row.get("kode_kabupaten_kota", ""))
            if kec_code and kab_code and not kec_code.startswith(kab_code):
                invalid_hierarchy.append(f"{row.get('nama_kecamatan', 'Unknown')}: {kec_code} does not start with {kab_code}")
        if invalid_hierarchy:
            errors.append(f"Hierarchical relationship errors: {invalid_hierarchy[:3]}")

    # Check for duplicate kecamatan names within same kabupaten/kota
    if all(col in df.columns for col in ["nama_kecamatan", "nama_kabupaten_kota"]):
        grouped_duplicates = {}
        for row in df.iter_rows(named=True):
            key = (row.get("nama_kabupaten_kota", ""), row.get("nama_kecamatan", ""))
            if key in grouped_duplicates:
                grouped_duplicates[key] += 1
            else:
                grouped_duplicates[key] = 1

        duplicates = [f"{kab_kota}.{kec} ({count})" for (kab_kota, kec), count in grouped_duplicates.items() if count > 1]
        if duplicates:
            errors.append(f"Duplicate kecamatan names within kabupaten/kota: {duplicates[:3]}")

    return errors


# Specific extraction functions
def _extract_single_province_kabupaten_kota(file_path: str, row: dict) -> tuple[Dict, list[str]]:
    """Extract data for a single province (kabupaten/kota tables)."""
    from extractor.pdf_table_extractor import PDFTableExtractor

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

    # Check for shutdown signal before starting heavy operations
    if shutdown_event.is_set():
        result.update({"time": 0.0, "error": "Task cancelled due to shutdown signal"})
        return result, log_messages

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

        # Validate extracted data
        validation_errors = _validate_kabupaten_kota_data(kabupaten_kota_index, province_name)

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
        log_messages.append(f"ERROR: Failed to extract {province_name}: {e}")

    return result, log_messages


# Public API functions
def _extract_single_province_kecamatan(file_path: str, row: dict) -> tuple[Dict, list[str]]:
    """Extract district data for a single province."""
    from extractor.pdf_table_extractor import PDFTableExtractor

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

    # Check for shutdown signal before starting heavy operations
    if shutdown_event.is_set():
        result.update({"time": 0.0, "error": "Task cancelled due to shutdown signal"})
        return result, log_messages

    try:
        table_extractor = PDFTableExtractor(file_path)
        kecamatan_index, unmatched_names = table_extractor.kecamatan_index(
            start_page=index_start, end_page=index_end, show_progress=False
        )

        extraction_time = time.time() - start_time
        result.update(
            {
                "success": True,
                "records": len(kecamatan_index),
                "time": extraction_time,
                "unmatched_names": unmatched_names,
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
        log_messages.append(f"ERROR: Failed to extract kecamatan for {province_name}: {e}")

    return result, log_messages


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
        "files": [],
    }

    log_messages = []

    # Check for shutdown signal before starting heavy operations
    if shutdown_event.is_set():
        result.update({"time": 0.0, "error": "Task cancelled due to shutdown signal"})
        return result, log_messages

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
            }
        )

        # Save table data using Polars native methods
        folder_name_base = sanitize_folder_file_name(province_name)
        filename_base = sanitize_folder_file_name(detail_name)
        path_base = os.path.join(folder_name_base, filename_base)
        json_debug_base = os.path.join(
            "debug", folder_name_base, filename_base
        )

        # CSV (tabular data)
        csv_path = get_csv_output_path(f"{path_base}.csv", ensure_dir=True)
        kabupaten_kota_detail.write_csv(csv_path)
        log_messages.append(f"INFO: Saved CSV for {detail_name}: {csv_path}")
        result["files"].append(csv_path)

        # Parquet (efficient storage)
        parquet_path = get_parquet_output_path(f"{path_base}.parquet", ensure_dir=True)
        kabupaten_kota_detail.write_parquet(parquet_path)
        log_messages.append(f"INFO: Saved Parquet for {detail_name}: {parquet_path}")
        result["files"].append(parquet_path)

        # JSON (DataFrame data only)
        json_path = get_json_output_path(f"{path_base}.json", ensure_dir=True)
        kabupaten_kota_detail.write_json(json_path)
        log_messages.append(f"INFO: Saved JSON for {detail_name}: {json_path}")
        result["files"].append(json_path)

        # Debug JSON (metadata + sample data)
        debug_data = {
            "name": detail_name,
            "page_range": {"start": detail_start, "end": detail_end},
            "table_format": detail_table_format,
            "row_count": len(kabupaten_kota_detail),
            "columns": kabupaten_kota_detail.columns,
            "sample_data": kabupaten_kota_detail.head(3).to_dicts(),
            "extraction_time_seconds": extraction_time,
            "validation_errors": [],  # Add validation if needed
        }
        debug_path = get_json_output_path(f"{json_debug_base}.json", ensure_dir=True)
        with open(debug_path, "w", encoding="utf-8") as f:
            json.dump(debug_data, f, ensure_ascii=False, indent=2)
        log_messages.append(f"INFO: Saved debug JSON for {detail_name}: {debug_path}")
        result["files"].append(debug_path)

    except Exception as e:
        extraction_time = time.time() - start_time
        result.update({"time": extraction_time, "error": str(e)})
        log_messages.append(f"ERROR: Failed to extract detail for {detail_name}: {e}")

    return result, log_messages
