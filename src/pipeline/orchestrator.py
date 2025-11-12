import json
import logging
import multiprocessing as mp
import os
import signal
import sys
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum

from dotenv import load_dotenv
from extractor.kode_wilayah_ocr import KodeWilayahOCR
from extractor.pdf_structure_extractor import PDFStructureExtractor
from extractor.pdf_table_extractor import PDFTableExtractor
from utils.paths import (
    ensure_output_dirs,
    get_csv_output_path,
    get_json_output_path,
    get_parquet_output_path,
    get_pdf_path,
    sanitize_folder_file_name
)
# Import removed - using config.settings instead
from .steps.structure_extraction import execute_structure_extraction
from .steps.province_index_extraction import execute_province_index_extraction
from .steps.kabupaten_kota_batch import execute_kabupaten_kota_batch
from .steps.kabupaten_kota_detail_batch import execute_kabupaten_kota_detail_batch
from .steps.kecamatan_batch import execute_kecamatan_batch

# Import the global shutdown event from batch_processor
from batch_processor import shutdown_event

logger = logging.getLogger(__name__)


class PipelineStep(Enum):
    """Enumeration of pipeline steps."""
    STRUCTURE_EXTRACTION = "structure_extraction"
    PROVINCE_INDEX_EXTRACTION = "province_index_extraction"
    KABUPATEN_KOTA_INDEX_BATCH = "kabupaten_kota_index_batch"
    KABUPATEN_KOTA_DETAIL_BATCH = "kabupaten_kota_detail_batch"
    KECAMATAN_INDEX_BATCH = "kecamatan_index_batch"


@dataclass
class PipelineConfig:
    """Configuration for the data pipeline."""
    main_pdf: str = ""
    batch_size: int = 38  # Default value, will be overridden by settings
    max_workers: int = 7   # Default value, will be overridden by settings
    province_filter: Optional[List[str]] = None
    debug_mode: bool = False
    force_restructure: bool = False
    log_level: str = "INFO"
    log_directory: str = "log"  # Default value, will be overridden by settings


@dataclass
class StepResult:
    """Result of a pipeline step execution."""
    step: PipelineStep
    success: bool
    start_time: datetime
    end_time: datetime
    records_processed: int = 0
    files_generated: List[str] = field(default_factory=list)
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def duration(self) -> float:
        """Calculate step duration in seconds."""
        return (self.end_time - self.start_time).total_seconds()


class PipelineOrchestrator:
    """Orchestrates the comprehensive data pipeline workflow."""

    def __init__(self, config: PipelineConfig):
        self.config = config
        self.step_results: List[StepResult] = []
        self.logger = logging.getLogger(__name__)
        self.shutdown_requested = False
        self.current_step: Optional[PipelineStep] = None
        self.state_file = os.path.join(config.log_directory, "pipeline_state.json")

        # Setup logging
        self._setup_logging()

        # Setup signal handlers for graceful shutdown
        self._setup_signal_handlers()

    def _setup_logging(self):
        """Setup logging configuration."""
        log_dir = self.config.log_directory
        os.makedirs(log_dir, exist_ok=True)
        log_filename = os.path.join(log_dir, datetime.now().strftime("pipeline-%Y%m%d-%H%M%S.log"))

        logging.basicConfig(
            level=getattr(logging, self.config.log_level),
            format="%(asctime)s - %(levelname)s - %(message)s",
            handlers=[
                logging.FileHandler(log_filename),
                logging.StreamHandler()
            ],
            force=True
        )

        # Ensure multiprocessing logger doesn't interfere
        mp_logger = mp.get_logger()
        mp_logger.setLevel(logging.WARNING)

    def _setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown."""
        def signal_handler(signum, frame):
            """Handle shutdown signals."""
            if not self.shutdown_requested:
                self.shutdown_requested = True
                shutdown_event.set()  # Set the global shutdown event for multiprocessing
                self.logger.warning("Shutdown signal received. Initiating graceful shutdown...")
                print("\nShutdown signal received. Waiting for current operations to complete...")

        # Register signal handlers
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

    def _save_state(self):
        """Save current pipeline state for resumability."""
        try:
            state = {
                "completed_steps": [step.step.value for step in self.step_results if step.success],
                "current_step": self.current_step.value if self.current_step else None,
                "timestamp": datetime.now().isoformat(),
                "config": {
                    "main_pdf": self.config.main_pdf,
                    "batch_size": self.config.batch_size,
                    "max_workers": self.config.max_workers,
                    "province_filter": self.config.province_filter,
                    "debug_mode": self.config.debug_mode,
                }
            }
            os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump(state, f, indent=2, ensure_ascii=False)
            self.logger.info(f"Pipeline state saved to {self.state_file}")
        except Exception as e:
            self.logger.warning(f"Failed to save pipeline state: {e}")

    def _load_state(self) -> Dict[str, Any]:
        """Load previous pipeline state."""
        if not os.path.exists(self.state_file):
            return {}

        try:
            with open(self.state_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            self.logger.warning(f"Failed to load pipeline state: {e}")
            return {}

    def _cleanup_resources(self):
        """Clean up temporary resources and files."""
        self.logger.info("Cleaning up temporary resources...")
        # Add cleanup logic here if needed
        # For now, just log that cleanup is happening
        print("🧹 Cleaning up temporary resources...")

    def _handle_shutdown(self):
        """Handle graceful shutdown of the pipeline."""
        print("\nInitiating graceful shutdown...")
        self.logger.warning("Pipeline shutdown initiated")

        # Clean up resources
        self._cleanup_resources()

        # Print shutdown summary
        completed_steps = [step for step in self.step_results if step.success]
        print(f"\nShutdown Summary:")
        print(f"   Completed steps: {len(completed_steps)}")
        print(f"   Pipeline interrupted - no state saved")
        print(f"   Run pipeline again to restart from beginning")

        # Clear shutdown event for potential future runs
        shutdown_event.clear()

        self.logger.info("Pipeline shutdown completed gracefully")

    def execute_pipeline(self) -> bool:
        """Execute the complete data pipeline."""
        self.logger.info("Starting comprehensive data pipeline execution")

        # Clear any previous shutdown state
        shutdown_event.clear()
        self.shutdown_requested = False

        # Load previous state if exists
        previous_state = self._load_state()
        completed_steps = set(previous_state.get("completed_steps", []))

        try:
            # Step 1: PDF Structure Analysis
            # Always check if structure file exists, even if step is marked as completed
            from utils.paths import get_json_output_path
            import os
            structure_path = get_json_output_path("structure_pdf.json")
            if PipelineStep.STRUCTURE_EXTRACTION.value not in completed_steps or not os.path.exists(structure_path):
                if not self._execute_step(PipelineStep.STRUCTURE_EXTRACTION):
                    return False
            else:
                self.logger.info(f"Skipping completed step: {PipelineStep.STRUCTURE_EXTRACTION.value}")

            # Check for shutdown request
            if self.shutdown_requested:
                self._handle_shutdown()
                return False

            # Step 2: Province Index Extraction
            if PipelineStep.PROVINCE_INDEX_EXTRACTION.value not in completed_steps:
                if not self._execute_step(PipelineStep.PROVINCE_INDEX_EXTRACTION):
                    return False
            else:
                self.logger.info(f"Skipping completed step: {PipelineStep.PROVINCE_INDEX_EXTRACTION.value}")

            # Check for shutdown request
            if self.shutdown_requested:
                self._handle_shutdown()
                return False

            # Step 3: Kabupaten/Kota Index Batch
            if PipelineStep.KABUPATEN_KOTA_INDEX_BATCH.value not in completed_steps:
                if not self._execute_step(PipelineStep.KABUPATEN_KOTA_INDEX_BATCH):
                    return False
            else:
                self.logger.info(f"Skipping completed step: {PipelineStep.KABUPATEN_KOTA_INDEX_BATCH.value}")

            # Check for shutdown request
            if self.shutdown_requested:
                self._handle_shutdown()
                return False

            # Step 4: Kecamatan Index Batch
            if PipelineStep.KECAMATAN_INDEX_BATCH.value not in completed_steps:
                if not self._execute_step(PipelineStep.KECAMATAN_INDEX_BATCH):
                    return False
            else:
                self.logger.info(f"Skipping completed step: {PipelineStep.KECAMATAN_INDEX_BATCH.value}")

            # Check for shutdown request
            if self.shutdown_requested:
                self._handle_shutdown()
                return False

            # Step 5: Kabupaten/Kota Detail Batch
            if PipelineStep.KABUPATEN_KOTA_DETAIL_BATCH.value not in completed_steps:
                if not self._execute_step(PipelineStep.KABUPATEN_KOTA_DETAIL_BATCH):
                    return False
            else:
                self.logger.info(f"Skipping completed step: {PipelineStep.KABUPATEN_KOTA_DETAIL_BATCH.value}")

            # Clean up state file on successful completion
            if os.path.exists(self.state_file):
                os.remove(self.state_file)
                self.logger.info("Pipeline completed successfully, removed state file")

            self.logger.info("Pipeline execution completed successfully")
            self._print_summary()
            return True

        except KeyboardInterrupt:
            # Ensure shutdown event is set for multiprocessing workers
            if not self.shutdown_requested:
                self.shutdown_requested = True
                shutdown_event.set()
            self._handle_shutdown()
            return False
        except Exception as e:
            self.logger.error(f"Pipeline execution failed: {e}")
            return False

    def _execute_step(self, step: PipelineStep) -> bool:
        """Execute a single pipeline step with error handling and tracking."""
        start_time = datetime.now()
        self.current_step = step
        self.logger.info(f"Starting step: {step.value}")

        try:
            result = None

            if step == PipelineStep.STRUCTURE_EXTRACTION:
                result = self._execute_structure_extraction()
            elif step == PipelineStep.PROVINCE_INDEX_EXTRACTION:
                result = self._execute_province_index_extraction()
            elif step == PipelineStep.KABUPATEN_KOTA_INDEX_BATCH:
                result = self._execute_kabupaten_kota_batch()
            elif step == PipelineStep.KABUPATEN_KOTA_DETAIL_BATCH:
                result = self._execute_kabupaten_kota_detail_batch()
            elif step == PipelineStep.KECAMATAN_INDEX_BATCH:
                result = self._execute_kecamatan_batch()

            if result and result.success:
                end_time = datetime.now()
                step_result = StepResult(
                    step=step,
                    success=True,
                    start_time=start_time,
                    end_time=end_time,
                    records_processed=result.records_processed,
                    files_generated=result.files_generated,
                    metadata=result.metadata
                )
                self.step_results.append(step_result)
                self.logger.info(f"Step {step.value} completed successfully in {step_result.duration:.2f}s")

                # Save state after successful step completion
                self._save_state()
                return True
            else:
                error_msg = result.error_message if result else "Unknown error"
                self.logger.error(f"Step {step.value} failed: {error_msg}")
                end_time = datetime.now()
                step_result = StepResult(
                    step=step,
                    success=False,
                    start_time=start_time,
                    end_time=end_time,
                    error_message=error_msg
                )
                self.step_results.append(step_result)
                return False

        except Exception as e:
            self.logger.error(f"Step {step.value} execution error: {e}")
            end_time = datetime.now()
            step_result = StepResult(
                step=step,
                success=False,
                start_time=start_time,
                end_time=end_time,
                error_message=str(e)
            )
            self.step_results.append(step_result)
            return False

    def _execute_structure_extraction(self) -> Optional[Any]:
        """Execute PDF structure extraction step."""
        return execute_structure_extraction(self.config, self.config.force_restructure, self.logger)

    def _execute_province_index_extraction(self) -> Optional[Any]:
        """Execute province index extraction step."""
        return execute_province_index_extraction(self.config, self.logger)


    def _execute_kabupaten_kota_batch(self) -> Optional[Any]:
        """Execute kabupaten/kota index batch processing."""
        return execute_kabupaten_kota_batch(self.config, self.logger)

    def _execute_kabupaten_kota_detail_batch(self) -> Optional[Any]:
        """Execute kabupaten/kota detail batch processing."""
        return execute_kabupaten_kota_detail_batch(self.config, self.logger)

    def _execute_kecamatan_batch(self) -> Optional[Any]:
        """Execute kecamatan index batch processing."""
        return execute_kecamatan_batch(self.config, self.logger)

    def _print_summary(self):
        """Print pipeline execution summary."""
        print("\n" + "="*60)
        print("PIPELINE EXECUTION SUMMARY")
        print("="*60)

        total_duration = sum(step.duration for step in self.step_results)
        total_records = sum(step.records_processed for step in self.step_results)
        total_files = sum(len(step.files_generated) for step in self.step_results)

        print(f"Total execution time: {total_duration:.2f} seconds")
        print(f"Total records processed: {total_records}")
        print(f"Total files generated: {total_files}")
        print()

        for step_result in self.step_results:
            status = "✓" if step_result.success else "✗"
            print(f"{status} {step_result.step.value}: {step_result.duration:.2f}s")
            if step_result.records_processed > 0:
                print(f"    Records: {step_result.records_processed}")
            if step_result.files_generated:
                print(f"    Files: {len(step_result.files_generated)}")
            if step_result.error_message:
                print(f"    Error: {step_result.error_message}")
            print()

        print("="*60)