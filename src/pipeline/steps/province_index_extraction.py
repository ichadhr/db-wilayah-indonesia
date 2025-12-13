import json
import os
from typing import Any, Optional

from config.settings import settings
from extractor.pdf_table_extractor import PDFTableExtractor
from utils.errors import BatchProcessingError, error_handler
from utils.paths import (
    get_json_output_path,
    get_parquet_output_path,
    sanitize_folder_file_name,
)
from utils.structure_utils import provinsi_index_struct

from ..validation import validate_province_data


@error_handler(operation_name="province_index_extraction", log_errors=True)
def execute_province_index_extraction(config, logger=None) -> Optional[Any]:
    """Execute province index extraction step."""
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

    # Get province index page ranges
    prov_df = provinsi_index_struct(structure_path)
    if len(prov_df) == 0:
        raise BatchProcessingError(
            "No province index found in structure", file_path=structure_path
        )

    prov_row = prov_df.row(0)
    index_name = prov_row[0]
    index_table_format = prov_row[1]
    index_start = prov_row[2]
    index_end = prov_row[3]

    table_extractor = PDFTableExtractor(pdf_path)
    provinsi_index_table = table_extractor.provinsi_index(
        start_page=index_start, end_page=index_end
    )

    logger.info(
        f"Extracted {len(provinsi_index_table)} province records from pages {index_start}-{index_end}"
    )

    # Validate province data
    validation_errors = validate_province_data(provinsi_index_table)
    if validation_errors:
        logger.warning(f"Province data validation issues: {validation_errors}")

    # Save table data
    filename_base = sanitize_folder_file_name(index_name)
    files_generated = []

    # Parquet
    parquet_path = get_parquet_output_path(f"{filename_base}.parquet", ensure_dir=True)
    provinsi_index_table.write_parquet(parquet_path)
    files_generated.append(parquet_path)

    # Debug JSON
    debug_data = {
        "name": index_name,
        "page_range": {"start": index_start, "end": index_end},
        "table_format": index_table_format,
        "row_count": len(provinsi_index_table),
        "columns": provinsi_index_table.columns,
        "sample_data": provinsi_index_table.head(3).to_dicts(),
        "validation_errors": validation_errors,
    }
    debug_path = get_json_output_path(
        f"{settings.pipeline.debug_directory}/{filename_base}.json", ensure_dir=True
    )
    with open(debug_path, "w", encoding="utf-8") as f:
        json.dump(debug_data, f, ensure_ascii=False, indent=2)
    files_generated.append(debug_path)

    return type(
        "Result",
        (),
        {
            "success": True,
            "records_processed": len(provinsi_index_table),
            "files_generated": files_generated,
            "metadata": {
                "page_range": f"{index_start}-{index_end}",
                "table_format": index_table_format,
                "validation_errors": len(validation_errors),
            },
        },
    )()
