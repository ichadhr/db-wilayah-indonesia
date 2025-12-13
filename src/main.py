import argparse
import logging
import os

from dotenv import load_dotenv

# Load environment variables before importing settings
# Use path relative to script location, not current working directory
env_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(env_path)

from config.settings import settings  # noqa: E402
from extractor.pos_wilayah import PosWilayahExtractor  # noqa: E402
from pipeline.orchestrator import PipelineConfig, PipelineOrchestrator  # noqa: E402
from utils.errors import BatchProcessingError, log_error  # noqa: E402
from utils.paths import (  # noqa: E402
    ensure_output_dirs,
    get_json_output_path,
    get_parquet_output_path,
)

logger = logging.getLogger(__name__)


def main():
    """Main entry point for the data pipeline."""
    parser = argparse.ArgumentParser(description="Run the data pipeline.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--provinsi-only",
        action="store_true",
        help="Run only the province index extraction step",
    )
    group.add_argument(
        "--kabupaten-only",
        action="store_true",
        help="Run only the kabupaten kota batch step",
    )
    group.add_argument(
        "--kecamatan-only",
        action="store_true",
        help="Run only the kecamatan index batch step for testing",
    )
    group.add_argument(
        "--details-only",
        action="store_true",
        help="Run only the kabupaten kota detail batch step",
    )
    group.add_argument(
        "--merge-only", action="store_true", help="Run only the parquet merge step"
    )
    group.add_argument(
        "--pos-only",
        action="store_true",
        help="Run only the postal code extraction step",
    )
    args = parser.parse_args()

    # Create pipeline configuration from settings
    config = PipelineConfig(
        main_pdf=settings.pipeline.main_pdf,
        batch_size=settings.pipeline.batch_size,
        max_workers=settings.pipeline.max_workers,
        province_filter=settings.pipeline.province_filter,
        debug_mode=settings.pipeline.debug_mode,
        force_restructure=settings.pipeline.force_restructure,
        log_level=settings.pipeline.log_level,
        log_directory=settings.pipeline.log_directory,
    )

    # Ensure output directories exist
    ensure_output_dirs()

    # Create orchestrator
    orchestrator = PipelineOrchestrator(config)

    if args.provinsi_only:
        # Run only the province index extraction step
        logger.info("Running province index extraction step only")
        kode_wilayah_file = get_parquet_output_path("kode_wilayah.parquet")
        if not os.path.exists(kode_wilayah_file):
            logger.info(
                "Kode wilayah parquet not found, executing kode wilayah extraction"
            )
            result = orchestrator.execute_kode_wilayah_extraction()
            if result and result.success:
                logger.info("Kode wilayah extraction completed successfully")
            else:
                error_msg = result.error_message if result else "Unknown error"
                log_error(
                    BatchProcessingError(
                        f"Kode wilayah extraction failed: {error_msg}",
                        operation="kode_wilayah_extraction",
                    ),
                    "main_pipeline",
                )
                exit(1)
        structure_file = get_json_output_path("structure_pdf.json")
        if not os.path.exists(structure_file):
            logger.info("Structure PDF JSON not found, executing structure extraction")
            result = orchestrator.execute_structure_extraction()
            if result and result.success:
                logger.info("Structure extraction completed successfully")
            else:
                error_msg = result.error_message if result else "Unknown error"
                log_error(
                    BatchProcessingError(
                        f"Structure extraction failed: {error_msg}",
                        operation="structure_extraction",
                    ),
                    "main_pipeline",
                )
                exit(1)
        result = orchestrator.execute_province_index_extraction()
        if result and result.success:
            logger.info("Province index extraction completed successfully")
        else:
            error_msg = result.error_message if result else "Unknown error"
            log_error(
                BatchProcessingError(
                    f"Province index extraction failed: {error_msg}",
                    operation="province_index_extraction",
                ),
                "main_pipeline",
            )
            exit(1)
    elif args.kabupaten_only:
        # Run only the kabupaten kota batch step
        logger.info("Running kabupaten kota batch step only")
        structure_file = get_json_output_path("structure_pdf.json")
        if not os.path.exists(structure_file):
            logger.info("Structure PDF JSON not found, executing structure extraction")
            result = orchestrator.execute_structure_extraction()
            if result and result.success:
                logger.info("Structure extraction completed successfully")
            else:
                error_msg = result.error_message if result else "Unknown error"
                logger.error(f"Structure extraction failed: {error_msg}")
                exit(1)
        result = orchestrator.execute_kabupaten_kota_batch()
        if result and result.success:
            logger.info("Kabupaten kota batch completed successfully")
        else:
            error_msg = result.error_message if result else "Unknown error"
            log_error(
                BatchProcessingError(
                    f"Kabupaten kota batch failed: {error_msg}",
                    operation="kabupaten_kota_batch",
                ),
                "main_pipeline",
            )
            exit(1)
    elif args.details_only:
        # Run only the kabupaten kota detail batch step
        logger.info("Running kabupaten kota detail batch step only")
        structure_file = get_json_output_path("structure_pdf.json")
        if not os.path.exists(structure_file):
            logger.info("Structure PDF JSON not found, executing structure extraction")
            result = orchestrator.execute_structure_extraction()
            if result and result.success:
                logger.info("Structure extraction completed successfully")
            else:
                error_msg = result.error_message if result else "Unknown error"
                logger.error(f"Structure extraction failed: {error_msg}")
                exit(1)
        result = orchestrator.execute_kabupaten_kota_detail_batch()
        if result and result.success:
            logger.info("Kabupaten kota detail batch completed successfully")
        else:
            error_msg = result.error_message if result else "Unknown error"
            log_error(
                BatchProcessingError(
                    f"Kabupaten kota detail batch failed: {error_msg}",
                    operation="kabupaten_kota_detail_batch",
                ),
                "main_pipeline",
            )
            exit(1)
    elif args.kecamatan_only:
        # Run only the kecamatan batch step
        logger.info("Running kecamatan index batch step only")
        kode_wilayah_file = get_parquet_output_path("kode_wilayah.parquet")
        if not os.path.exists(kode_wilayah_file):
            logger.info(
                "Kode wilayah parquet not found, executing kode wilayah extraction"
            )
            result = orchestrator.execute_kode_wilayah_extraction()
            if result and result.success:
                logger.info("Kode wilayah extraction completed successfully")
            else:
                error_msg = result.error_message if result else "Unknown error"
                logger.error(f"Kode wilayah extraction failed: {error_msg}")
                exit(1)
        structure_file = get_json_output_path("structure_pdf.json")
        if not os.path.exists(structure_file):
            logger.info("Structure PDF JSON not found, executing structure extraction")
            result = orchestrator.execute_structure_extraction()
            if result and result.success:
                logger.info("Structure extraction completed successfully")
            else:
                error_msg = result.error_message if result else "Unknown error"
                logger.error(f"Structure extraction failed: {error_msg}")
                exit(1)
        result = orchestrator.execute_kecamatan_batch()
        if result and result.success:
            logger.info("Kecamatan index batch completed successfully")
        else:
            error_msg = result.error_message if result else "Unknown error"
            log_error(
                BatchProcessingError(
                    f"Kecamatan index batch failed: {error_msg}",
                    operation="kecamatan_batch",
                ),
                "main_pipeline",
            )
            exit(1)
    elif args.merge_only:
        # Run only the parquet merge step
        logger.info("Running parquet merge step only")
        from pipeline.steps.parquet_merge import execute_parquet_merge

        result = execute_parquet_merge(logger)
        if result and result.success:
            logger.info("Parquet merge completed successfully")
        else:
            error_msg = result.error_message if result else "Unknown error"
            log_error(
                BatchProcessingError(
                    f"Parquet merge failed: {error_msg}", operation="parquet_merge"
                ),
                "main_pipeline",
            )
            exit(1)
    elif args.pos_only:
        # Run only the postal code extraction step
        logger.info("Running postal code extraction step only")
        extractor = PosWilayahExtractor(
            parquet_dir="output", max_workers=config.max_workers
        )
        stats = extractor.extract_pos_wilayah(
            logger=logger, province_filter=config.province_filter
        )
        if stats["total_processed"] > 0:
            logger.info("Postal code extraction completed successfully")
        else:
            log_error(
                BatchProcessingError(
                    "Postal code extraction failed: no data processed",
                    operation="pos_extraction",
                ),
                "main_pipeline",
            )
            exit(1)
    else:
        # Execute full pipeline
        success = orchestrator.execute_pipeline()

        if not success:
            logger.error("Pipeline execution failed")
            exit(1)
        else:
            logger.info("Pipeline execution completed successfully")


if __name__ == "__main__":
    main()
