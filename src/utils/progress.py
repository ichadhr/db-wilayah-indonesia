"""
tqdm-based progress utilities for PDF processing operations.

This module provides progress bars with statistics support,
migrated from Rich to tqdm for simpler dependency management.
"""

from contextlib import contextmanager
from typing import Optional

from tqdm import tqdm

from utils.errors import error_handler


class ProgressManager:
    """Centralized progress management for PDF processing operations."""

    def __init__(self):
        self.active_progresses = {}

    @contextmanager
    @error_handler(operation_name="pdf_processing_progress", log_errors=True, re_raise=False)
    def pdf_processing_progress(
        self,
        total_pages: int,
        description: str = "Processing PDF",
    ):
        """Context manager for PDF processing with table-format-specific descriptions."""
        # Create tqdm progress bar with custom format
        progress_bar = tqdm(
            total=total_pages,
            desc=description,
            unit="page",
            bar_format="{desc}: {percentage:3.0f}%|{bar}| {n}/{total} [{elapsed} < {remaining}{postfix}]",
        )

        # Set initial postfix
        rate = progress_bar.format_dict.get("rate", 0) or 0
        progress_bar.set_postfix_str(
            f"{rate:.0f} pages/s, 0 Provinsi, 0 Kabupaten/Kota"
        )

        progress_context = PDFProgressContext(progress_bar, total_pages)
        try:
            yield progress_context
        finally:
            progress_bar.close()

    @contextmanager
    @error_handler(operation_name="table_extraction_progress", log_errors=True, re_raise=False)
    def table_extraction_progress(
        self,
        total_pages: int,
        description: str = "Extracting table",
    ):
        """Context manager for table extraction progress tracking."""
        # Create tqdm progress bar for table extraction
        progress_bar = tqdm(
            total=total_pages,
            desc=description,
            unit="page",
            bar_format="{desc}: {percentage:3.0f}%|{bar}| {n}/{total} [{elapsed} < {remaining}{postfix}]",
        )

        # Set initial postfix
        progress_bar.set_postfix_str(f"0 Pages, 0 Records")

        progress_context = TableExtractionProgressContext(progress_bar, total_pages)
        try:
            yield progress_context
        finally:
            progress_bar.close()

    @contextmanager
    @error_handler(operation_name="download_progress", log_errors=True, re_raise=False)
    def download_progress(self, total_items: int, description: str = "Downloading"):
        """Context manager for download operations."""
        # Create tqdm progress bar for downloads
        progress_bar = tqdm(
            total=total_items,
            desc=description,
            unit="item",
            bar_format="{desc} {percentage:3.0f}%|{bar}| {n}/{total} [{elapsed} < {remaining}{postfix}]",
        )

        # Set initial postfix
        rate = progress_bar.format_dict.get("rate", 0) or 0
        progress_bar.set_postfix_str(f"{rate:.0f} items/s")

        progress_context = DownloadProgressContext(progress_bar, total_items)
        try:
            yield progress_context
        finally:
            progress_bar.close()

    @contextmanager
    @error_handler(operation_name="batch_processing_progress", log_errors=True, re_raise=False)
    def batch_processing_progress(
        self,
        total_items: int,
        item_name: str = "items",
        description: str = "Processing batch",
    ):
        """Context manager for batch processing operations."""
        # Create tqdm progress bar for batch processing
        progress_bar = tqdm(
            total=total_items,
            desc=description,
            unit=item_name,
            bar_format="{desc}: {percentage:3.0f}%|{bar}| {n}/{total} [{elapsed} < {remaining}]",
        )

        progress_context = BatchProgressContext(progress_bar, total_items)
        try:
            yield progress_context
        finally:
            progress_bar.close()


class PDFProgressContext:
    """Context for PDF processing progress tracking."""

    def __init__(self, progress_bar: tqdm, total_pages: int):
        self.progress_bar = progress_bar
        self.total_pages = total_pages
        self.stats = {
            "pages_processed": 0,
            "provinces_found": 0,
            "kabupaten_kota_count": 0,
        }

    def update_stats(
        self,
        provinces_found: Optional[int] = None,
        kabupaten_kota_count: Optional[int] = None,
        **kwargs,
    ):
        """Update progress statistics."""
        if provinces_found is not None:
            self.stats["provinces_found"] = provinces_found
        if kabupaten_kota_count is not None:
            self.stats["kabupaten_kota_count"] = kabupaten_kota_count

        # Update any additional stats
        self.stats.update(kwargs)

        # Update postfix with rate and stats
        rate = self.progress_bar.format_dict.get("rate", 0) or 0
        stats_text = f"{rate:.0f} pages/s, {self.stats['provinces_found']} Provinsi, {self.stats['kabupaten_kota_count']} Kabupaten/Kota"
        self.progress_bar.set_postfix_str(stats_text)

    def advance(self, pages: int = 1):
        """Advance progress by specified number of pages."""
        self.stats["pages_processed"] += pages
        self.progress_bar.update(pages)


class DownloadProgressContext:
    """Context for download progress tracking."""

    def __init__(self, progress_bar: tqdm, total_items: int):
        self.progress_bar = progress_bar
        self.total_items = total_items

    def advance(self, items: int = 1):
        """Advance progress by specified number of items."""
        self.progress_bar.update(items)
        # Update postfix with current rate
        rate = self.progress_bar.format_dict.get("rate", 0) or 0
        self.progress_bar.set_postfix_str(f"{rate:.0f} items/s")

    def update(self, description: str):
        """Update the progress bar description."""
        self.progress_bar.set_description(description)


class TableExtractionProgressContext:
    """Context for table extraction progress tracking."""

    def __init__(self, progress_bar: tqdm, total_pages: int):
        self.progress_bar = progress_bar
        self.total_pages = total_pages
        self.stats = {
            "pages_processed": 0,
            "records_extracted": 0,
        }

    def update_records(self, records: int):
        """Update the number of records extracted."""
        self.stats["records_extracted"] += records
        self._update_postfix()

    def advance(self, pages: int = 1):
        """Advance progress by specified number of pages."""
        self.stats["pages_processed"] += pages
        self.progress_bar.update(pages)
        self._update_postfix()

    def get_total_records(self) -> int:
        """Get the total number of records extracted."""
        return self.stats["records_extracted"]

    def _update_postfix(self):
        """Update the progress bar postfix with current statistics."""
        pages = self.stats["pages_processed"]
        records = self.stats["records_extracted"]
        self.progress_bar.set_postfix_str(f"{pages} Pages, {records} Records")


class BatchProgressContext:
    """Context for batch processing progress tracking."""

    def __init__(self, progress_bar: tqdm, total_items: int):
        self.progress_bar = progress_bar
        self.total_items = total_items

    def advance(self, items: int = 1):
        """Advance progress by specified number of items."""
        self.progress_bar.update(items)


# Global instance for easy access
progress_manager = ProgressManager()
