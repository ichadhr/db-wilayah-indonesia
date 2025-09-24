# Utils package

from .errors import (
    PDFExtractorError,
    PDFStructureError,
    TableExtractionError,
    FileOperationError,
    NetworkError,
    ValidationError,
    ConfigurationError,
    error_handler,
    log_error,
    create_error_report,
    safe_execute,
    handle_file_not_found,
    handle_network_timeout,
    handle_validation_failure,
    handle_pdf_corruption
)

__all__ = [
    'PDFExtractorError',
    'PDFStructureError',
    'TableExtractionError',
    'FileOperationError',
    'NetworkError',
    'ValidationError',
    'ConfigurationError',
    'error_handler',
    'log_error',
    'create_error_report',
    'safe_execute',
    'handle_file_not_found',
    'handle_network_timeout',
    'handle_validation_failure',
    'handle_pdf_corruption'
]