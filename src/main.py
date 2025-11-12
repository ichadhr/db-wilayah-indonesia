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

    # Create and execute pipeline
    orchestrator = PipelineOrchestrator(config)
    success = orchestrator.execute_pipeline()

    if not success:
        logger.error("Pipeline execution failed")
        exit(1)
    else:
        logger.info("Pipeline execution completed successfully")


if __name__ == "__main__":
    main()
