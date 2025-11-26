# Utils package

# Error handling
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

# Path utilities
from .paths import (
    get_project_root,
    get_datas_dir,
    get_output_dir,
    get_output_subdir,
    ensure_output_dirs,
    get_pdf_path,
    get_csv_output_path,
    get_json_output_path,
    get_parquet_output_path,
    get_image_output_path,
    sanitize_folder_file_name
)

# Correction utilities
from .correction import CorrectionLoader

# Data merger utilities
from .data_merger import ParquetFileMerger

# Text normalization and conversion utilities
from .text_utils import (
    format_number,
    format_luas,
    format_pulau,
    format_string,
    format_text,
    normalize_for_matching,
    convert_cyrillic_to_latin,
    normalize_kabupaten_kota,
    normalize_kecamatan,
    normalize_kelurahan_desa,
    kode_wilayah
)

# Progress tracking
from .progress import progress_manager

__all__ = [
    # Error handling
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
    'handle_pdf_corruption',
    # Path utilities
    'get_project_root',
    'get_datas_dir',
    'get_output_dir',
    'get_output_subdir',
    'ensure_output_dirs',
    'get_pdf_path',
    'get_csv_output_path',
    'get_json_output_path',
    'get_parquet_output_path',
    'get_image_output_path',
    'sanitize_folder_file_name',
    # Correction
    'CorrectionLoader',
    # Data merger
    'ParquetFileMerger',
    # Normalization
    'format_number',
    'format_luas',
    'format_pulau',
    'format_string',
    'format_text',
    'normalize_for_matching',
    'convert_cyrillic_to_latin',
    'normalize_kabupaten_kota',
    'normalize_kecamatan',
    'normalize_kelurahan_desa',
    'kode_wilayah',
    # Progress
    'progress_manager',
]