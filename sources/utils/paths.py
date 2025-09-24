"""
Centralized path utilities for the db-wilayah-indonesia project.

This module provides consistent path handling for datas/ and output/ directories
across all scripts in the project.
"""

import os
from pathlib import Path


def get_project_root() -> str:
    """
    Get the sources/ directory path (project root for scripts).

    This function finds the sources/ directory by going up from any script location.
    It assumes that utils/ is always inside sources/.
    """
    # Get the directory of this paths.py file
    utils_dir = os.path.dirname(__file__)
    # Go up one level to get sources/
    project_root = os.path.dirname(utils_dir)
    return project_root


def get_datas_dir() -> str:
    """Get the sources/datas/ directory path."""
    return os.path.join(get_project_root(), "datas")


def get_output_dir() -> str:
    """Get the sources/output/ directory path."""
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


def ensure_output_dirs() -> None:
    """Create all output subdirectories if they don't exist."""
    output_dir = get_output_dir()
    subdirs = ["json", "csv", "parquet", "images"]

    for subdir in subdirs:
        full_path = os.path.join(output_dir, subdir)
        os.makedirs(full_path, exist_ok=True)


# Convenience functions for common paths
def get_pdf_path(filename: str) -> str:
    """Get full path to a PDF file in datas/ directory."""
    return os.path.join(get_datas_dir(), filename)


def ensure_file_directory(filepath: str) -> None:
    """
    Ensure the directory for a file path exists.

    Args:
        filepath: Full path to a file (not just directory)
    """
    directory = os.path.dirname(filepath)
    if directory and not os.path.exists(directory):
        os.makedirs(directory, exist_ok=True)


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