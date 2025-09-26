import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional

from dotenv import load_dotenv
from extractor.kode_wilayah_ocr import KodeWilayahOCR
from extractor.pdf_structure import PDFStructureExtractor
from extractor.pdf_table import PDFTableExtractor
from utils.paths import (
    ensure_output_dirs,
    get_csv_output_path,
    get_json_output_path,
    get_parquet_output_path,
    get_pdf_path,
    sanitize_folder_file_name,
)
from utils.progress import progress_manager
from utils.structure_utils import (
    kabupaten_kota_detail_struct,
    kabupaten_kota_index_struct,
    kecamatan_index_struct,
    provinsi_index_struct,
)

# Constants
DEBUG_JSON_FOLDER = "debug"
BATCH_SIZE = 38  # Number of provinces per batch
MAX_WORKERS = 8  # Concurrent workers (set to 1 for sequential processing)
PROVINCE_FILTER = ["Aceh", "Sumatera Utara"]  # Specific provinces to process [Optional]

# Setup logging
from datetime import datetime

log_filename = datetime.now().strftime('extraction-%Y%m%d-%H%M%S.log')
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_filename)
        # Removed StreamHandler to avoid console clutter during progress bars
    ]
)
logger = logging.getLogger(__name__)


def main():
    # init dotenv
    load_dotenv()

    MAIN_PDF = os.getenv("MAIN_PDF") or ""

    # Find administrative structure
    pdf_path = get_pdf_path(MAIN_PDF)

    # Ensure output directories exist
    ensure_output_dirs()

    # structure_json_path = extract_structure(pdf_path)
    # temporary
    structure_json_path = get_json_output_path("structure_pdf.json")
    if not structure_json_path:
        raise ValueError("Failed to extract structure")

    extract_table_kabupaten_kota_index_batch(
        pdf_path,
        structure_json_path,
        # province_filter=PROVINCE_FILTER,
        batch_size=BATCH_SIZE,
        max_workers=MAX_WORKERS,
        log_filename=log_filename,
    )


def extract_pdf_structure(doc_path: str):
    try:
        print("Starting scanning PDF document...")
        extractor = PDFStructureExtractor(doc_path)
        structure = extractor.extract_structure()

        # Validate the structure
        print("Validating structure...")
        validation = extractor.validate_structure()

        if validation["valid"]:
            print(f"\nExtraction successful!")
            print(f"Found {validation['province_count']} provinces")
            print(f"Found {validation['total_details']} total kabupaten/kota")
        else:
            print(f"\nExtraction completed with issues:")
            for issue in validation["issues"]:
                print(f"  - {issue}")

        # Outputs as JSON
        structure_json_path = get_json_output_path("structure_pdf.json")
        with open(structure_json_path, "w", encoding="utf-8") as f:
            json.dump(structure.model_dump(), f, ensure_ascii=False, indent=2)
        print(f"Successfully structured PDF document {structure_json_path}.")

        return structure_json_path

    except Exception as e:
        print(f"Error during get PDF structure: {e}")


def extract_table_provinsi_index(file_path: str, structure_path: str):
    try:
        # Get province index page ranges using utility
        prov_df = provinsi_index_struct(structure_path)
        if len(prov_df) == 0:
            raise ValueError("No province index found in structure")

        prov_row = prov_df.row(0)
        index_name = prov_row[0]  # name column
        index_table_format = prov_row[1]  # table_format column
        index_start = prov_row[2]  # start_page column
        index_end = prov_row[3]  # end_page column

        table_extractor = PDFTableExtractor(file_path)
        provinsi_index_table = table_extractor.provinsi_index(
            start_page=index_start, end_page=index_end
        )

        print(
            f"Extracted {len(provinsi_index_table)} province records from pages {index_start}-{index_end}"
        )

        # Save table data using Polars native methods
        filename_base = sanitize_folder_file_name(index_name)
        json_debug_base = os.path.join(DEBUG_JSON_FOLDER, filename_base)

        # CSV (tabular data)
        csv_path = get_csv_output_path(f"{filename_base}.csv", ensure_dir=True)
        provinsi_index_table.write_csv(csv_path)
        print(f"Table data saved to {csv_path}")

        # Parquet (efficient storage)
        parquet_path = get_parquet_output_path(
            f"{filename_base}.parquet", ensure_dir=True
        )
        provinsi_index_table.write_parquet(parquet_path)
        print(f"Table data saved to {parquet_path}")

        # JSON (DataFrame data only)
        json_path = get_json_output_path(f"{filename_base}.json", ensure_dir=True)
        provinsi_index_table.write_json(json_path)
        print(f"Table data saved to {json_path}")

        # Debug JSON (metadata + sample data) in debug folder
        debug_data = {
            "name": index_name,
            "page_range": {"start": index_start, "end": index_end},
            "table_format": index_table_format,
            "row_count": len(provinsi_index_table),
            "columns": provinsi_index_table.columns,
            "sample_data": provinsi_index_table.head(3).to_dicts(),
        }
        debug_path = get_json_output_path(f"{json_debug_base}.json", ensure_dir=True)
        with open(debug_path, "w", encoding="utf-8") as f:
            json.dump(debug_data, f, ensure_ascii=False, indent=2)
        print(f"Debug info saved to {debug_path}")

    except Exception as e:
        print(f"Error during Province table extraction: {e}")


def extract_table_kabupaten_kota_index(file_path: str, structure_path: str):
    province_name = "Unknown"  # Initialize for error reporting
    try:
        # Get district/city index page ranges using utility
        district_city_df = kabupaten_kota_index_struct(structure_path)
        if len(district_city_df) == 0:
            raise ValueError("No district/city index found in structure")

        district_city_row = district_city_df.row(0)
        province_name = district_city_row[0]  # province column
        index_name = district_city_row[2]  # name column
        index_table_format = district_city_row[3]  # table_format column
        index_start = district_city_row[4]  # start_page column
        index_end = district_city_row[5]  # end_page column

        table_extractor = PDFTableExtractor(file_path)
        kabupaten_kota_index = table_extractor.kabupaten_kota_index(
            start_page=index_start, end_page=index_end, show_progress=False
        )

        print(
            f"Extracted {len(kabupaten_kota_index)} district/city records for {province_name} from pages {index_start}-{index_end}"
        )

        # Save table data using Polars native methods
        foldername_base = sanitize_folder_file_name(province_name)
        filename_base = sanitize_folder_file_name(index_name)
        path_base = os.path.join(foldername_base, filename_base)
        json_debug_base = os.path.join(
            DEBUG_JSON_FOLDER, foldername_base, filename_base
        )

        # CSV (tabular data)
        csv_path = get_csv_output_path(f"{path_base}.csv", ensure_dir=True)
        kabupaten_kota_index.write_csv(csv_path)
        print(f"Table data saved to {csv_path}")

        # Parquet (efficient storage)
        parquet_path = get_parquet_output_path(f"{path_base}.parquet", ensure_dir=True)
        kabupaten_kota_index.write_parquet(parquet_path)
        print(f"Table data saved to {parquet_path}")

        # JSON (DataFrame data only)
        json_path = get_json_output_path(f"{path_base}.json", ensure_dir=True)
        kabupaten_kota_index.write_json(json_path)
        print(f"Table data saved to {json_path}")

        # Debug JSON (metadata + sample data) in debug folder
        debug_data = {
            "name": index_name,
            "page_range": {"start": index_start, "end": index_end},
            "table_format": index_table_format,
            "row_count": len(kabupaten_kota_index),
            "columns": kabupaten_kota_index.columns,
            "sample_data": kabupaten_kota_index.head(3).to_dicts(),
        }
        debug_path = get_json_output_path(f"{json_debug_base}.json", ensure_dir=True)
        with open(debug_path, "w", encoding="utf-8") as f:
            json.dump(debug_data, f, ensure_ascii=False, indent=2)
        print(f"Debug info saved to {debug_path}")

    except Exception as e:
        print(
            f"Error during District/City table extraction for Province {province_name}: {e}"
        )


def extract_table_kabupaten_kota_index_batch(
    file_path: str,
    structure_path: str,
    province_filter: Optional[List[str]] = None,
    batch_size: int = 3,
    max_workers: int = 2,
    log_filename: Optional[str] = None,
):
    """
    Extract district/city index tables for multiple provinces in batches.

    Args:
        file_path: Path to PDF file
        structure_path: Path to structure JSON
        province_filter: Optional list of province names to process
        batch_size: Number of provinces to process per batch
        max_workers: Maximum concurrent workers
        log_filename: Optional log filename for summary display
    """
    try:
        # Get all district/city index sections
        district_city_df = kabupaten_kota_index_struct(structure_path, province_filter)
        if len(district_city_df) == 0:
            raise ValueError("No district/city index found in structure")

        total_provinces = len(district_city_df)
        if max_workers == 1:
            print(f"Processing {total_provinces} provinces sequentially")
        else:
            print(
                f"Processing {total_provinces} provinces in batches of {min(batch_size, total_provinces)}"
            )

        # Process in batches
        for batch_start in range(0, total_provinces, batch_size):
            batch_end = min(batch_start + batch_size, total_provinces)
            batch_df = district_city_df.slice(batch_start, batch_end - batch_start)

            if max_workers == 1:
                province_name = batch_df.row(0)[0]  # province_name is the first column
                print(f"\nProcessing province {batch_start + 1}: {province_name}")
            else:
                print(
                    f"\nProcessing batch {batch_start//batch_size + 1}: provinces {batch_start + 1}-{batch_end}"
                )

            # Show batch progress
            batch_num = batch_start // batch_size + 1
            total_batches = (total_provinces + batch_size - 1) // batch_size
            print(f"Batch {batch_num}/{total_batches} - Starting extraction...")

            # Process batch with optional parallelization and progress tracking
            if max_workers > 1:
                _process_batch_parallel_with_progress(file_path, batch_df, max_workers)
            else:
                _process_batch_sequential_with_progress(file_path, batch_df)

            print(f"Batch {batch_num}/{total_batches} - Completed ✓")

            # Memory cleanup between batches
            import gc

            gc.collect()

    except Exception as e:
        print(f"Error during batch District/City table extraction: {e}")


def _process_batch_sequential_with_progress(file_path: str, batch_df):
    """Process a batch of provinces sequentially with progress bar."""
    rows = list(batch_df.iter_rows(named=True))
    results = []

    with progress_manager.batch_processing_progress(
        total_items=len(rows),
        item_name="province",
        description="Processing provinces"
    ) as progress_context:
        for row in rows:
            result = _extract_single_province(file_path, row)
            results.append(result)
            progress_context.advance(1)

    _print_batch_summary(results, log_filename)


def _process_batch_parallel_with_progress(file_path: str, batch_df, max_workers: int):
    """Process a batch of provinces in parallel with progress bar."""
    rows = list(batch_df.iter_rows(named=True))
    results = []

    with progress_manager.batch_processing_progress(
        total_items=len(rows),
        item_name="province",
        description="Processing provinces"
    ) as progress_context:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            future_to_row = {
                executor.submit(_extract_single_province, file_path, row): row
                for row in rows
            }

            # Collect results as they complete
            for future in as_completed(future_to_row):
                row = future_to_row[future]
                result = future.result()  # Get the result dict
                results.append(result)
                progress_context.advance(1)

    _print_batch_summary(results, log_filename)


def _extract_single_province(file_path: str, row: dict) -> Dict:
    """Extract data for a single province and return result dict."""
    province_name = row["province_name"]
    index_name = row["name"]
    index_table_format = row["table_format"]
    index_start = row["start_page"]
    index_end = row["end_page"]

    start_time = time.time()
    result = {
        'province_name': province_name,
        'success': False,
        'records': None,
        'time': None,
        'error': None,
        'page_range': (index_start, index_end),
        'files': []
    }

    try:
        table_extractor = PDFTableExtractor(file_path)
        kabupaten_kota_index = table_extractor.kabupaten_kota_index(
            start_page=index_start, end_page=index_end, show_progress=False
        )

        extraction_time = time.time() - start_time
        result.update({
            'success': True,
            'records': len(kabupaten_kota_index),
            'time': extraction_time
        })

        # Save table data using Polars native methods
        foldername_base = sanitize_folder_file_name(province_name)
        filename_base = sanitize_folder_file_name(index_name)
        path_base = os.path.join(foldername_base, filename_base)
        json_debug_base = os.path.join(
            DEBUG_JSON_FOLDER, foldername_base, filename_base
        )

        # CSV (tabular data)
        csv_path = get_csv_output_path(f"{path_base}.csv", ensure_dir=True)
        kabupaten_kota_index.write_csv(csv_path)
        logger.info(f"Saved CSV for {province_name}: {csv_path}")
        result['files'].append(csv_path)

        # Parquet (efficient storage)
        parquet_path = get_parquet_output_path(f"{path_base}.parquet", ensure_dir=True)
        kabupaten_kota_index.write_parquet(parquet_path)
        logger.info(f"Saved Parquet for {province_name}: {parquet_path}")
        result['files'].append(parquet_path)

        # JSON (DataFrame data only)
        json_path = get_json_output_path(f"{path_base}.json", ensure_dir=True)
        kabupaten_kota_index.write_json(json_path)
        logger.info(f"Saved JSON for {province_name}: {json_path}")
        result['files'].append(json_path)

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
        logger.info(f"Saved debug JSON for {province_name}: {debug_path}")
        result['files'].append(debug_path)

    except Exception as e:
        extraction_time = time.time() - start_time
        result.update({
            'time': extraction_time,
            'error': str(e)
        })
        logger.error(f"Failed to extract {province_name}: {e}")

    return result


def _print_batch_summary(results: List[Dict], log_filename: Optional[str] = None):
    """Print a summary of batch processing results."""
    successful = [r for r in results if r['success']]
    failed = [r for r in results if not r['success']]

    print(f"✓ {len(successful)} provinces processed successfully")
    for result in successful:
        records = result['records']
        time_taken = result['time']
        province = result['province_name']
        if records == 0:
            start, end = result['page_range']
            print(f"  - {province}: found 0 records, range page {start}-{end}")
        else:
            print(f"  - {province}: {records} records in {time_taken:.2f}s")

    if failed:
        print(f"✗ {len(failed)} provinces failed")
        for result in failed:
            province = result['province_name']
            error = result['error']
            print(f"  - {province}: {error}")

    if log_filename:
        print(f"\n📄 Detailed logs saved to: {log_filename}")


def extract_code_wilayah():
    try:
        # Extract kode wilayah data using OCR
        print("Starting kode wilayah OCR extraction...")
        ocr_extractor = KodeWilayahOCR()
        kode_wilayah_data = ocr_extractor.extract_kode_wilayah()

        print(
            f"Successfully extracted {len(kode_wilayah_data.records)} kode wilayah records."
        )
        print("Data saved to output directories (parquet, csv, json).")
    except Exception as e:
        print(f"Error during OCR extraction: {e}")


if __name__ == "__main__":
    main()
