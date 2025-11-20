import json
from typing import Optional, Any

from extractor.kode_wilayah_ocr import KodeWilayahOCR
from utils.paths import (
    get_json_output_path,
    get_parquet_output_path,
    sanitize_folder_file_name
)
from config.settings import settings
from ..validation import validate_kode_wilayah_data
import polars as pl


def execute_kode_wilayah_extraction(config, logger=None) -> Optional[Any]:
    """Execute kode wilayah extraction step."""
    if logger is None:
        import logging
        logger = logging.getLogger(__name__)

    # Initialize OCR extractor
    extractor = KodeWilayahOCR()

    # Extract kode wilayah data
    kode_wilayah_table = extractor.extract_kode_wilayah(logger)

    logger.info(f"Extracted {len(kode_wilayah_table.records)} kode wilayah records")

    # Convert to DataFrame for saving
    df_clean = pl.DataFrame([r.model_dump() for r in kode_wilayah_table.records])

    # Validate kode wilayah data
    validation_errors = validate_kode_wilayah_data(df_clean)
    if validation_errors:
        logger.warning(f"Kode wilayah data validation issues: {validation_errors}")

    # Save table data
    filename_base = sanitize_folder_file_name("kode_wilayah")
    files_generated = []


    # Parquet
    parquet_path = get_parquet_output_path(f"{filename_base}.parquet", ensure_dir=True)
    df_clean.write_parquet(parquet_path)
    files_generated.append(parquet_path)


    # Debug JSON
    debug_data = {
        "name": "kode_wilayah",
        "row_count": len(df_clean),
        "columns": df_clean.columns,
        "sample_data": df_clean.head(3).to_dicts(),
    }
    debug_path = get_json_output_path(f"{settings.pipeline.debug_directory}/{filename_base}.json", ensure_dir=True)
    with open(debug_path, "w", encoding="utf-8") as f:
        json.dump(debug_data, f, ensure_ascii=False, indent=2)
    files_generated.append(debug_path)

    return type('Result', (), {
        'success': True,
        'records_processed': len(df_clean),
        'files_generated': files_generated,
        'metadata': {
            'extraction_method': 'ocr',
            'source': 'SNI_7657-2023',
            'validation_errors': len(validation_errors)
        }
    })()