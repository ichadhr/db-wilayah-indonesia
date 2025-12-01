"""
Global error handling utilities for the PDF extraction application.

This module provides custom exception classes and error handling utilities
to ensure consistent error reporting and handling across the application.
"""

import logging
import sys
import traceback
from contextlib import contextmanager
from datetime import datetime, UTC
from typing import Any, Dict, Optional

# Configure logger
logger = logging.getLogger(__name__)


class PDFExtractorError(Exception):
    """Base exception class for PDF extraction errors."""

    def __init__(
        self,
        message: str,
        error_code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        **kwargs,
    ):
        self.message = message
        self.error_code = error_code or "PDF_EXTRACTOR_ERROR"
        self.details = details or {}
        self.details.update(kwargs)
        super().__init__(self.message)


class PDFStructureError(PDFExtractorError):
    """Exception raised when PDF structure analysis fails."""

    def __init__(self, message: str, page_num: Optional[int] = None, **kwargs):
        super().__init__(message, error_code="PDF_STRUCTURE_ERROR", **kwargs)
        self.page_num = page_num
        if page_num is not None:
            self.details["page_number"] = page_num


class TableExtractionError(PDFExtractorError):
    """Exception raised when table extraction fails."""

    def __init__(self, message: str, table_format: Optional[str] = None, **kwargs):
        super().__init__(message, error_code="TABLE_EXTRACTION_ERROR", **kwargs)
        self.table_format = table_format
        if table_format:
            self.details["table_format"] = table_format


class FileOperationError(PDFExtractorError):
    """Exception raised when file operations fail."""

    def __init__(
        self,
        message: str,
        file_path: Optional[str] = None,
        operation: Optional[str] = None,
        **kwargs,
    ):
        super().__init__(message, error_code="FILE_OPERATION_ERROR", **kwargs)
        self.file_path = file_path
        self.operation = operation
        if file_path:
            self.details["file_path"] = file_path
        if operation:
            self.details["operation"] = operation


class NetworkError(PDFExtractorError):
    """Exception raised when network operations fail."""

    def __init__(
        self,
        message: str,
        url: Optional[str] = None,
        status_code: Optional[int] = None,
        **kwargs,
    ):
        super().__init__(message, error_code="NETWORK_ERROR", **kwargs)
        self.url = url
        self.status_code = status_code
        if url:
            self.details["url"] = url
        if status_code:
            self.details["status_code"] = status_code


class ValidationError(PDFExtractorError):
    """Exception raised when data validation fails."""

    def __init__(
        self,
        message: str,
        field: Optional[str] = None,
        value: Optional[Any] = None,
        **kwargs,
    ):
        super().__init__(message, error_code="VALIDATION_ERROR", **kwargs)
        self.field = field
        self.value = value
        if field:
            self.details["field"] = field
        if value is not None:
            self.details["value"] = str(value)


class ConfigurationError(PDFExtractorError):
    """Exception raised when configuration is invalid."""

    def __init__(self, message: str, config_key: Optional[str] = None, **kwargs):
        super().__init__(message, error_code="CONFIGURATION_ERROR", **kwargs)
        self.config_key = config_key
        if config_key:
            self.details["config_key"] = config_key


class BatchProcessingError(PDFExtractorError):
    """Exception raised when batch processing fails."""

    def __init__(self, message: str, batch_id: Optional[str] = None, **kwargs):
        super().__init__(message, error_code="BATCH_PROCESSING_ERROR", **kwargs)
        self.batch_id = batch_id
        if batch_id:
            self.details["batch_id"] = batch_id


class OCRError(PDFExtractorError):
    """Exception raised when OCR processing fails."""

    def __init__(self, message: str, ocr_engine: Optional[str] = None, **kwargs):
        super().__init__(message, error_code="OCR_ERROR", **kwargs)
        self.ocr_engine = ocr_engine
        if ocr_engine:
            self.details["ocr_engine"] = ocr_engine


@contextmanager
def error_handler(
    operation_name: str = "operation", log_errors: bool = True, re_raise: bool = True
):
    """
    Context manager for consistent error handling.

    Args:
        operation_name: Name of the operation for logging
        log_errors: Whether to log errors
        re_raise: Whether to re-raise exceptions after logging
    """
    try:
        yield
    except PDFExtractorError:
        # Re-raise our custom errors as-is
        if log_errors:
            logger.error(
                f"PDF Extractor error in {operation_name}: {str(sys.exc_info()[1])}"
            )
        if re_raise:
            raise
    except Exception as e:  # noqa: broad-except
        # Wrap unexpected errors in our base exception
        error_msg = f"Unexpected error in {operation_name}: {str(e)}"
        if log_errors:
            logger.error(error_msg)
            logger.debug(f"Traceback: {traceback.format_exc()}")

        if re_raise:
            raise PDFExtractorError(
                error_msg,
                error_code="UNEXPECTED_ERROR",
                details={"original_error": str(e), "traceback": traceback.format_exc()},
            )


def log_error(
    error: Exception, operation: str = "operation", level: str = "error"
) -> None:
    """
    Log an error with consistent formatting.

    Args:
        error: The exception to log
        operation: Name of the operation where error occurred
        level: Logging level ('debug', 'info', 'warning', 'error', 'critical')
    """
    LOG_METHODS = {
        'debug': logger.debug,
        'info': logger.info,
        'warning': logger.warning,
        'error': logger.error,
        'critical': logger.critical
    }
    log_func = LOG_METHODS.get(level, logger.error)

    if isinstance(error, PDFExtractorError):
        log_func(
            f"PDF Extractor error in {operation} [{error.error_code}]: {error.message}"
        )
        if error.details:
            logger.debug(f"Error details: {error.details}")
    else:
        log_func(f"Unexpected error in {operation}: {str(error)}")
        logger.debug(f"Traceback: {traceback.format_exc()}")


def create_error_report(
    error: Exception, context: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Create a comprehensive error report.

    Args:
        error: The exception that occurred
        context: Additional context information

    Returns:
        Dictionary containing error report
    """
    report: Dict[str, Any] = {
        "error_type": type(error).__name__,
        "error_message": str(error),
        "timestamp": datetime.now(UTC).isoformat(),
        "traceback": traceback.format_exc(),
    }

    if isinstance(error, PDFExtractorError):
        report["error_code"] = error.error_code
        report["details"] = error.details

    if context:
        report["context"] = context

    return report


def safe_execute(
    func, *args, operation_name: str = "function", default_return=None, **kwargs
):
    """
    Execute a function safely with error handling.

    Args:
        func: Function to execute
        *args: Positional arguments for the function
        operation_name: Name of the operation for logging
        default_return: Value to return on error
        **kwargs: Keyword arguments for the function

    Returns:
        Function result or default_return on error
    """
    try:
        with error_handler(operation_name, log_errors=True, re_raise=False):
            return func(*args, **kwargs)
    except Exception:  # noqa: broad-except
        return default_return


# Convenience functions for common error patterns
def handle_file_not_found(file_path: str, operation: str = "file_operation") -> None:
    """Handle file not found errors."""
    raise FileOperationError(
        f"File not found: {file_path}", file_path=file_path, operation=operation
    )


def handle_network_timeout(url: str, timeout: int) -> None:
    """Handle network timeout errors."""
    raise NetworkError(f"Network timeout after {timeout}s: {url}", url=url)


def handle_validation_failure(field: str, value: Any, reason: str) -> None:
    """Handle validation failures."""
    raise ValidationError(
        f"Validation failed for {field}: {reason}", field=field, value=value
    )


def handle_pdf_corruption(file_path: str, reason: str) -> None:
    """Handle corrupted PDF files."""
    raise PDFStructureError(
        f"PDF file appears to be corrupted: {reason}", details={"file_path": file_path}
    )
