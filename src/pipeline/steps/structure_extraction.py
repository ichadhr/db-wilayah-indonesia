import json
import os
from typing import Optional, Any

from extractor.pdf_structure_extractor import PDFStructureExtractor
from utils.cache_utils import get_pdf_metadata, load_cached_structure_with_validation
from utils.errors import BatchProcessingError, error_handler, log_error
from utils.paths import get_json_output_path


@error_handler(operation_name="structure_extraction", log_errors=True)
def execute_structure_extraction(config, force_restructure: bool = False, force_regeneration: Optional[str] = None, logger=None) -> Optional[Any]:
    """
    Execute PDF structure extraction step with intelligent caching.

    Args:
        config: Configuration object containing main_pdf path
        force_restructure: Legacy parameter, forces regeneration (deprecated, use force_regeneration)
        force_regeneration: Force regeneration mode:
            - None: Use intelligent caching (default)
            - 'always' or 'force': Always regenerate, ignore cache
        logger: Optional logger instance

    Returns:
        Result object with success status and metadata
    """
    if logger is None:
        import logging
        logger = logging.getLogger(__name__)

    structure_path = get_json_output_path("structure_pdf.json")
    pdf_path = config.main_pdf

    # Check if PDF exists
    if not os.path.exists(pdf_path):
        raise BatchProcessingError(f"PDF file not found: {pdf_path}", file_path=pdf_path)

    # Determine if we should skip caching
    skip_cache = force_restructure or force_regeneration in ['always', 'force']

    # Check cache validity if not skipping
    if not skip_cache:
        cached_structure = load_cached_structure_with_validation(structure_path, pdf_path)
        if cached_structure is not None:
            logger.info("Valid cached structure found, skipping extraction")
            return type('Result', (), {
                'success': True,
                'records_processed': 0,
                'files_generated': [structure_path],
                'metadata': {'cached': True, 'cache_valid': True}
            })()
        elif os.path.exists(structure_path):
            logger.info("Cached structure exists but is invalid (PDF changed), regenerating")

    # Get cache metadata first
    cache_metadata = get_pdf_metadata(pdf_path)

    # Extract structure with cache metadata
    extractor = PDFStructureExtractor(pdf_path)
    structure = extractor.extract_structure(cache_metadata)

    # Validate the structure
    validation = extractor.validate_structure()
    if not validation["valid"]:
        logger.warning(f"Structure validation issues: {validation['issues']}")

    # Save structure with metadata
    with open(structure_path, "w", encoding="utf-8") as f:
        json.dump(structure.model_dump(exclude_none=False), f, ensure_ascii=False, indent=2)

    return type('Result', (), {
        'success': True,
        'records_processed': validation.get('province_count', 0),
        'files_generated': [structure_path],
        'metadata': {**validation, 'cache_updated': True}
    })()