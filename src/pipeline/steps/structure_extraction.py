import json
import os
from typing import Optional, Any

from extractor.pdf_structure_extractor import PDFStructureExtractor
from utils.paths import get_json_output_path


def execute_structure_extraction(config, force_restructure: bool = False, logger=None) -> Optional[Any]:
    """Execute PDF structure extraction step."""
    if logger is None:
        import logging
        logger = logging.getLogger(__name__)

    # Check if structure already exists and not forcing restructure
    structure_path = get_json_output_path("structure_pdf.json")
    if os.path.exists(structure_path) and not force_restructure:
        logger.info("Structure file already exists, skipping extraction")
        return type('Result', (), {
            'success': True,
            'records_processed': 0,
            'files_generated': [structure_path],
            'metadata': {'cached': True}
        })()

    pdf_path = config.main_pdf
    if not os.path.exists(pdf_path):
        raise ValueError(f"PDF file not found: {pdf_path}")

    extractor = PDFStructureExtractor(pdf_path)
    structure = extractor.extract_structure()

    # Validate the structure
    validation = extractor.validate_structure()
    if not validation["valid"]:
        logger.warning(f"Structure validation issues: {validation['issues']}")

    # Save structure
    with open(structure_path, "w", encoding="utf-8") as f:
        json.dump(structure.model_dump(), f, ensure_ascii=False, indent=2)

    return type('Result', (), {
        'success': True,
        'records_processed': validation.get('province_count', 0),
        'files_generated': [structure_path],
        'metadata': validation
    })()