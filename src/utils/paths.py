"""
Centralized path utilities for the db-wilayah-indonesia project.

This module provides consistent path handling for datas/ and output/ directories
across all scripts in the project.
"""

import os

from utils.errors import FileOperationError, error_handler


def get_project_root() -> str:
    """
    Get the src/ directory path (project root for scripts).

    This function finds the src/ directory by going up from any script location.
    It assumes that utils/ is always inside src/.
    """
    # Get the directory of these paths.py file
    utils_dir = os.path.dirname(__file__)
    # Go up one level to get src/
    project_root = os.path.dirname(utils_dir)
    return project_root


def get_datas_dir() -> str:
    """Get the src/datas/ directory path."""
    return os.path.join(get_project_root(), "datas")


def get_output_dir() -> str:
    """Get the src/output/ directory path."""
    return os.path.join(get_project_root(), "output")


def get_output_subdir(subdir: str) -> str:
    """
    Get output subdirectory path (json, csv, parquet, images).

    Args:
        subdir: Subdirectory name (e.g., 'json', 'csv', 'parquet', 'images')

    Returns:
        Full path to the output subdirectory
    """
    return os.path.join(get_output_dir(), subdir)


@error_handler(operation_name="ensure_output_dirs", log_errors=True)
def ensure_output_dirs() -> None:
    """Create all output subdirectories if they don't exist."""
    output_dir = get_output_dir()
    subdirs = ["json", "csv", "parquet", "images"]

    for subdir in subdirs:
        full_path = os.path.join(output_dir, subdir)
        try:
            os.makedirs(full_path, exist_ok=True)
        except OSError as e:
            raise FileOperationError(
                f"Failed to create output subdirectory: {full_path}",
                file_path=full_path,
                operation="create_directory"
            ) from e

    # Create debug subdirectory under json
    debug_dir = os.path.join(get_output_subdir("json"), "debug")
    try:
        os.makedirs(debug_dir, exist_ok=True)
    except OSError as e:
        raise FileOperationError(
            f"Failed to create debug subdirectory: {debug_dir}",
            file_path=debug_dir,
            operation="create_directory"
        ) from e


# Convenience functions for common paths
def get_pdf_path(filename: str) -> str:
    """Get full path to a PDF file in datas/ directory."""
    return os.path.join(get_datas_dir(), filename)


@error_handler(operation_name="ensure_file_directory", log_errors=True)
def ensure_file_directory(filepath: str) -> None:
    """
    Ensure the directory for a file path exists.

    Args:
        filepath: Full path to a file (not just directory)
    """
    directory = os.path.dirname(filepath)
    if directory and not os.path.exists(directory):
        try:
            os.makedirs(directory, exist_ok=True)
        except OSError as e:
            raise FileOperationError(
                f"Failed to create directory for file: {directory}",
                file_path=directory,
                operation="create_directory"
            ) from e


def get_csv_output_path(filename: str, ensure_dir: bool = False) -> str:
    """
    Get full path for CSV output file.

    Args:
        filename: Filename or relative path within csv/ directory
        ensure_dir: If True, create parent directories if they don't exist

    Returns:
        Full path to the CSV file
    """
    path = os.path.join(get_output_subdir("csv"), filename)
    if ensure_dir:
        ensure_file_directory(path)
    return path


def get_json_output_path(filename: str, ensure_dir: bool = False) -> str:
    """
    Get full path for JSON output file.

    Args:
        filename: Filename or relative path within json/ directory
        ensure_dir: If True, create parent directories if they don't exist

    Returns:
        Full path to the JSON file
    """
    path = os.path.join(get_output_subdir("json"), filename)
    if ensure_dir:
        ensure_file_directory(path)
    return path


def get_parquet_output_path(filename: str, ensure_dir: bool = False) -> str:
    """
    Get full path for Parquet output file.

    Args:
        filename: Filename or relative path within parquet/ directory
        ensure_dir: If True, create parent directories if they don't exist

    Returns:
        Full path to the Parquet file
    """
    path = os.path.join(get_output_subdir("parquet"), filename)
    if ensure_dir:
        ensure_file_directory(path)
    return path


def get_image_output_path(filename: str, ensure_dir: bool = False) -> str:
    """
    Get full path for image output file.

    Args:
        filename: Filename or relative path within images/ directory
        ensure_dir: If True, create parent directories if they don't exist

    Returns:
        Full path to the image file
    """
    path = os.path.join(get_output_subdir("images"), filename)
    if ensure_dir:
        ensure_file_directory(path)
    return path


def sanitize_folder_file_name(name: str) -> str:
    """
    Sanitize a name for use as a filename.

    Args:
        name: Original name string

    Returns:
        Sanitized filename (lowercase, spaces and slashes replaced with underscores)
    """
    return name.lower().replace(" ", "_").replace("/", "_")
