import argparse
import logging
import os
from dotenv import load_dotenv

# Load environment variables before importing settings
# Use path relative to script location, not current working directory
env_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(env_path)

from config.settings import settings
from pipeline.orchestrator import PipelineOrchestrator, PipelineConfig
from utils.paths import ensure_output_dirs

logger = logging.getLogger(__name__)


def main():
    """Main entry point for the data pipeline."""
    parser = argparse.ArgumentParser(description="Run the data pipeline.")
    parser.add_argument(
        "--kecamatan-only",
        action="store_true",
        help="Run only the kecamatan index batch step for testing"
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
        log_directory=settings.pipeline.log_directory
    )

    # Ensure output directories exist
    ensure_output_dirs()

    # Create orchestrator
    orchestrator = PipelineOrchestrator(config)

    if args.kecamatan_only:
        # Run only the kecamatan batch step
        logger.info("Running kecamatan index batch step only")
        result = orchestrator._execute_kecamatan_batch()
        if result and result.success:
            logger.info("Kecamatan index batch completed successfully")
        else:
            error_msg = result.error_message if result else "Unknown error"
            logger.error(f"Kecamatan index batch failed: {error_msg}")
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
