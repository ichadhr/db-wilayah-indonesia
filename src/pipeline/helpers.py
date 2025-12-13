import gc
import json
import os

from config.settings import settings
from extractor.kode_wilayah_ocr import KodeWilayahOCR
from extractor.pdf_structure_extractor import PDFStructureExtractor
from extractor.pdf_table_extractor import PDFTableExtractor
from utils.errors import (
    FileOperationError,
    OCRError,
    TableExtractionError,
    ValidationError,
    error_handler,
    log_error,
)
from utils.paths import (
    get_csv_output_path,
    get_json_output_path,
    get_parquet_output_path,
    sanitize_folder_file_name,
)
from utils.structure_utils import (
    kabupaten_kota_index_struct,
    kecamatan_index_struct,
    provinsi_index_struct,
)

from .batch_processor import BatchProcessor, _extract_single_province_kabupaten_kota


@error_handler(operation_name="extract_pdf_structure", log_errors=True, re_raise=False)
def extract_pdf_structure(doc_path: str):
    try:
        print("Starting scanning PDF document...")
        extractor = PDFStructureExtractor(doc_path)
        structure = extractor.extract_structure()

        # Validate the structure
        print("Validating structure...")
        structure_validation = extractor.validate_structure()
        PDFStructureExtractor.print_validation_result(structure_validation)

        # Outputs as JSON
        structure_json_path = get_json_output_path("structure_pdf.json")
        with open(structure_json_path, "w", encoding="utf-8") as f:
            json.dump(structure.model_dump(), f, ensure_ascii=False, indent=2)
        print(f"Successfully structured PDF document {structure_json_path}.")

        return structure_json_path

    except (FileOperationError, ValidationError) as e:
        log_error(e, "extract_pdf_structure", "error")
        print(f"Error during get PDF structure: {e}")
    except Exception as e:
        log_error(e, "extract_pdf_structure", "error")
        print(f"Error during get PDF structure: {e}")


@error_handler(
    operation_name="extract_table_provinsi_index", log_errors=True, re_raise=False
)
def extract_table_provinsi_index(file_path: str, structure_path: str):
    try:
        # Get province index page ranges using utility
        prov_df = provinsi_index_struct(structure_path)
        if len(prov_df) == 0:
            raise ValidationError(
                "No province index found in structure",
                field="structure_data",
                value=structure_path,
            )

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
        json_debug_base = os.path.join(settings.pipeline.debug_directory, filename_base)

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

    except (ValidationError, TableExtractionError, FileOperationError) as e:
        log_error(e, "extract_table_provinsi_index", "error")
        print(f"Error during Province table extraction: {e}")
    except Exception as e:
        log_error(e, "extract_table_provinsi_index", "error")
        print(f"Error during Province table extraction: {e}")


@error_handler(
    operation_name="extract_table_kabupaten_kota_index", log_errors=True, re_raise=False
)
def extract_table_kabupaten_kota_index(file_path: str, structure_path: str):
    province_name = "Unknown"  # Initialize for error reporting
    try:
        # Get regency index page ranges using utility
        regency_df = kabupaten_kota_index_struct(structure_path)
        if len(regency_df) == 0:
            raise ValidationError(
                "No regency index found in structure",
                field="structure_data",
                value=structure_path,
            )

        regency_row = regency_df.row(0)
        province_name = regency_row[0]  # province column
        index_name = regency_row[2]  # name column
        index_table_format = regency_row[3]  # table_format column
        index_start = regency_row[4]  # start_page column
        index_end = regency_row[5]  # end_page column

        table_extractor = PDFTableExtractor(file_path)
        kabupaten_kota_index = table_extractor.kabupaten_kota_index(
            start_page=index_start, end_page=index_end, show_progress=False
        )

        print(
            f"Extracted {len(kabupaten_kota_index)} regency records for {province_name} from pages {index_start}-{index_end}"
        )

        # Save table data using Polars native methods
        folder_name_base = sanitize_folder_file_name(province_name)
        filename_base = sanitize_folder_file_name(index_name)
        path_base = os.path.join(folder_name_base, filename_base)
        json_debug_base = os.path.join(
            settings.pipeline.debug_directory, folder_name_base, filename_base
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

    except (ValidationError, TableExtractionError, FileOperationError) as e:
        log_error(e, "extract_table_kabupaten_kota_index", "error")
        print(
            f"Error during District/City table extraction for Province {province_name}: {e}"
        )
    except Exception as e:
        log_error(e, "extract_table_kabupaten_kota_index", "error")
        print(
            f"Error during District/City table extraction for Province {province_name}: {e}"
        )


@error_handler(
    operation_name="extract_table_kecamatan_index", log_errors=True, re_raise=False
)
def extract_table_kecamatan_index(file_path: str, structure_path: str):
    province_name = "Unknown"  # Initialize for error reporting
    try:
        # Get district/city index page ranges using utility
        district_df = kecamatan_index_struct(structure_path)
        if len(district_df) == 0:
            raise ValidationError(
                "No district index found in structure",
                field="structure_data",
                value=structure_path,
            )

        print(district_df)

        district_row = district_df.row(0)
        province_name = district_row[0]  # province column
        index_name = district_row[2]  # name column
        index_table_format = district_row[3]  # table_format column
        index_start = district_row[4]  # start_page column
        index_end = district_row[5]  # end_page column

        table_extractor = PDFTableExtractor(file_path)
        # kecamatan_index returns (df, unmatched_pdf_cities, unmapped_bsni_cities)
        # The latter two are logged internally by the extractor
        kecamatan_index, _, _ = table_extractor.kecamatan_index(
            start_page=index_start, end_page=index_end, show_progress=False
        )

        print(
            f"Extracted {len(kecamatan_index)} district records for {province_name} from pages {index_start}-{index_end}"
        )

        # Save table data using Polars native methods
        folder_name_base = sanitize_folder_file_name(province_name)
        filename_base = sanitize_folder_file_name(index_name)
        path_base = os.path.join(folder_name_base, filename_base)
        json_debug_base = os.path.join(
            settings.pipeline.debug_directory, folder_name_base, filename_base
        )

        # CSV (tabular data)
        csv_path = get_csv_output_path(f"{path_base}.csv", ensure_dir=True)
        # CSV/JSON output disabled for kecamatan - data only saved as parquet
        print(f"Table data saved to {csv_path}")

        # Parquet (efficient storage)
        parquet_path = get_parquet_output_path(f"{path_base}.parquet", ensure_dir=True)
        kecamatan_index.write_parquet(parquet_path)
        print(f"Table data saved to {parquet_path}")

        # JSON (DataFrame data only)
        json_path = get_json_output_path(f"{path_base}.json", ensure_dir=True)
        # kecamatan_index.write_json(json_path)
        print(f"Table data saved to {json_path}")

        # Debug JSON (metadata + sample data) in debug folder
        debug_data = {
            "name": index_name,
            "page_range": {"start": index_start, "end": index_end},
            "table_format": index_table_format,
            "row_count": len(kecamatan_index),
            "columns": kecamatan_index.columns,
            "sample_data": kecamatan_index.head(3).to_dicts(),
        }
        debug_path = get_json_output_path(f"{json_debug_base}.json", ensure_dir=True)
        with open(debug_path, "w", encoding="utf-8") as f:
            json.dump(debug_data, f, ensure_ascii=False, indent=2)
        print(f"Debug info saved to {debug_path}")

    except (ValidationError, TableExtractionError, FileOperationError) as e:
        log_error(e, "extract_table_kecamatan_index", "error")
        print(
            f"Error during District table extraction for Province {province_name}: {e}"
        )
    except Exception as e:
        log_error(e, "extract_table_kecamatan_index", "error")
        print(
            f"Error during District table extraction for Province {province_name}: {e}"
        )


def extract_table_kabupaten_kota_index_batch(
    file_path: str,
    structure_path: str,
    province_filter=None,
    batch_size: int = 38,
    max_workers: int = 7,
    log_filename=None,
):
    """
    Process kabupaten/kota index tables for multiple provinces in batches.

    Args:
        file_path: Path to PDF file
        structure_path: Path to structure JSON
        province_filter: Optional list of province names to process
        batch_size: Number of provinces to process per batch
        max_workers: Maximum concurrent workers
        log_filename: Optional log filename for summary display
    """

    # Get all regency index sections
    district_city_df = kabupaten_kota_index_struct(structure_path, province_filter)
    if len(district_city_df) == 0:
        raise ValidationError(
            "No regency index found in structure",
            field="structure_data",
            value=structure_path,
        )

    total_provinces = len(district_city_df)
    if max_workers == 1:
        print(f"Processing {total_provinces} provinces sequentially")
    else:
        print(
            f"Processing {total_provinces} provinces in batches of {min(batch_size, total_provinces)}"
        )

    processor = BatchProcessor(max_workers)
    all_results = []

    # Process in batches
    for batch_start in range(0, total_provinces, batch_size):
        batch_end = min(batch_start + batch_size, total_provinces)
        batch_df = district_city_df.slice(batch_start, batch_end - batch_start)

        if max_workers == 1:
            province_name = batch_df.row(0)[0]  # province_name is the first column
            print(f"\nProcessing province {batch_start + 1}: {province_name}")
        else:
            print(
                f"\nProcessing batch {batch_start // batch_size + 1}: provinces {batch_start + 1}-{batch_end}"
            )

        # Show batch progress
        batch_num = batch_start // batch_size + 1
        total_batches = (total_provinces + batch_size - 1) // batch_size
        print(f"Batch {batch_num}/{total_batches} - Starting extraction...")

        # Process batch with optional parallelization and progress tracking
        if max_workers > 1:
            results = processor.process_batch(
                file_path,
                batch_df,
                _extract_single_province_kabupaten_kota,
                item_name="province",
                log_filename=log_filename,
            )
        else:
            results = BatchProcessor.process_sequential(
                file_path,
                batch_df,
                _extract_single_province_kabupaten_kota,
                item_name="province",
                log_filename=log_filename,
            )

        all_results.extend(results)
        print(f"Batch {batch_num}/{total_batches} - Completed ✓")

        # Memory cleanup between batches
        gc.collect()

    return all_results


@error_handler(operation_name="extract_code_wilayah", log_errors=True, re_raise=False)
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
    except OCRError as e:
        log_error(e, "extract_code_wilayah", "error")
        print(f"Error during OCR extraction: {e}")
    except Exception as e:
        log_error(e, "extract_code_wilayah", "error")
        print(f"Error during OCR extraction: {e}")
