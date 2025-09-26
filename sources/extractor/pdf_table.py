import os
from typing import Any, List, Optional

import pdfplumber
import polars as pl
from models.pdf_table import DistrictCityIndexData, ProvinceIndexData
from utils.converter import *
from utils.progress import progress_manager


class PDFTableExtractorBase:
    """
    Base class to extract tables from PDF files using pdfplumber.
    """

    def __init__(
        self, pdf_path: str, start_page: int = 1, end_page: Optional[int] = None
    ):
        """
        Initialize the PDF Table Extractor.

        Args:
            pdf_path: Path to the PDF file to extract tables from
            start_page: Starting page number (1-based, inclusive)
            end_page: Ending page number (1-based, inclusive). If None, process to end
        """
        self.pdf_path = pdf_path
        self.start_page = start_page
        self.end_page = end_page
        self.index_settings = {
            "vertical_strategy": "lines",
            "horizontal_strategy": "lines",
        }

    def extract_tables(
        self, table_format: str = "unknown", show_progress: bool = True
    ) -> List[List[Any]]:
        """
        Extract tables from the specified page range of the PDF.

        Args:
            table_format: Format of the table being extracted (for progress display)

        Returns:
            List of table rows with duplicate headers merged
        """
        records = []
        with pdfplumber.open(self.pdf_path) as pdf:
            if pdf.pages:
                end_page = (
                    self.end_page if self.end_page is not None else len(pdf.pages)
                )
                total_pages = min(end_page, len(pdf.pages)) - (self.start_page - 1)

                if show_progress:
                    with progress_manager.table_extraction_progress(
                        total_pages=total_pages,
                        table_format=table_format,
                        description=f"Extracting {table_format.replace('_', ' ')} table",
                    ) as progress_ctx:
                        for i in range(
                            self.start_page - 1, min(end_page, len(pdf.pages))
                        ):
                            page = pdf.pages[i]
                            table = page.extract_table(self.index_settings)
                            if table is not None:
                                page_records = 0
                                for row in table:
                                    if any(row):
                                        records.append(row)
                                        page_records += 1
                                progress_ctx.update_records(page_records)
                            progress_ctx.advance(1)
                else:
                    # Extract without progress display
                    for i in range(self.start_page - 1, min(end_page, len(pdf.pages))):
                        page = pdf.pages[i]
                        table = page.extract_table(self.index_settings)
                        if table is not None:
                            for row in table:
                                if any(row):
                                    records.append(row)
        return self.merge_headers(records)

    def extract_table_from_page(self, page_num: int) -> Optional[List[List[Any]]]:
        """
        Extract table from a specific page within the configured range.

        Args:
            page_num: Page number to extract from (1-based, relative to start_page)

        Returns:
            Table data or None if no table found
        """
        with pdfplumber.open(self.pdf_path) as pdf:
            absolute_page_num = self.start_page + page_num - 1
            if (
                pdf.pages
                and absolute_page_num < len(pdf.pages)
                and (self.end_page is None or absolute_page_num <= self.end_page - 1)
            ):
                page = pdf.pages[absolute_page_num]
                return page.extract_table(self.index_settings)
        return None

    def merge_headers(self, merged_rows: List[List[Any]]) -> List[List[Any]]:
        """
        Merge table data by removing duplicate header blocks from multi-page extractions.

        Auto-detects header size by finding the first data row (typically starting with numbers).

        Args:
            merged_rows: Raw merged rows from extract_tables

        Returns:
            Cleaned rows with duplicate headers removed
        """
        if not merged_rows:
            return merged_rows

        # Auto-detect header size by finding first data row
        header_size = 0
        for i, row in enumerate(merged_rows):
            if row and len(row) > 0:
                first_cell = str(row[0]).strip()
                # Data rows typically start with numbers (province codes, etc.)
                if first_cell.isdigit():
                    header_size = i
                    break

        if header_size == 0:
            return merged_rows  # No clear headers detected

        # Extract header block
        header_block = merged_rows[:header_size]
        cleaned_rows = header_block.copy()

        # Process remaining rows, skipping duplicate headers
        i = header_size
        while i < len(merged_rows):
            if (
                i + header_size <= len(merged_rows)
                and merged_rows[i : i + header_size] == header_block
            ):
                i += header_size  # Skip duplicate header block
            else:
                cleaned_rows.append(merged_rows[i])
                i += 1

        return cleaned_rows


class PDFTableExtractor(PDFTableExtractorBase):
    """
    Child class of PDFTableExtractor with specific methods for extracting province-related tables.
    """

    def provinsi_index(self, start_page: int, end_page: int) -> pl.DataFrame:
        """
        Extract province index table.

        Args:
            start_page: Starting page number (1-based)
            end_page: Ending page number (1-based, inclusive)

        Returns:
            Polars DataFrame with province index data
        """
        # Use specific settings for province index tables
        provinsi_index_settings = {
            "vertical_strategy": "lines",
            "horizontal_strategy": "text",
            "snap_y_tolerance": 7,
            "intersection_x_tolerance": 15,
        }
        table_rows = self._extract_with_settings(
            start_page, end_page, provinsi_index_settings, table_format="provinsi_index"
        )

        # Convert table rows to ProvinceIndexData objects
        province_index_data = []
        for row in table_rows:
            if len(row) >= 11:  # Ensure row has enough columns
                # Skip header/summary rows
                first_cell = str(row[0]).strip() if row[0] else ""
                third_cell = str(row[2]).strip() if len(row) > 2 and row[2] else ""

                # Skip if first column is not numeric, or third column (province) is numeric
                if not (first_cell and first_cell.isdigit()) or third_cell.isdigit():
                    continue  # Skip header/summary rows

                try:
                    data = ProvinceIndexData(
                        no=row[0],
                        kode=row[1],
                        provinsi=row[2],
                        jumlah_kabupaten=row[3],
                        jumlah_kota=row[4],
                        jumlah_kecamatan=row[5],
                        jumlah_kelurahan=row[6],
                        jumlah_desa=row[7],
                        luas_wilayah_km2=row[8],
                        jumlah_penduduk=row[9],
                        jumlah_pulau=row[10],
                    )
                    province_index_data.append(data)
                except (ValueError, IndexError) as e:
                    raise ValueError(f"Failed to parse table row {row}: {e}")

        return pl.DataFrame([data.model_dump() for data in province_index_data])

    def kabupaten_kota_index(
        self, start_page: int, end_page: int, show_progress: bool = True
    ) -> pl.DataFrame:
        """
        Extract district/city index table.

        Args:
            start_page: Starting page number (1-based)
            end_page: Ending page number (1-based, inclusive)

        Returns:
            Polars DataFrame with province district/city data
        """
        # Use specific settings for district/city index tables
        kabupaten_kota_index_settings = {
            "vertical_strategy": "lines",
            "horizontal_strategy": "text",
            "snap_y_tolerance": 7,
            "intersection_x_tolerance": 300,
        }
        table_rows = self._extract_with_settings(
            start_page,
            end_page,
            kabupaten_kota_index_settings,
            table_format="kabupaten_kota_index",
            show_progress=show_progress,
        )

        # Convert table rows to DistrictCityIndexData objects
        district_city_data = []
        i = 0
        while i < len(table_rows):
            row = table_rows[i]
            if len(row) >= 9 and None not in row:
                first_cell = str(row[0]).strip() if row[0] else ""
                if first_cell and first_cell.isdigit():
                    # Start of data row
                    keterangan = str(row[8]) if row[8] else ""
                    i += 1
                    # Merge continuation rows
                    while i < len(table_rows):
                        next_row = table_rows[i]
                        if (
                            len(next_row) >= 9
                            and None not in next_row
                            and str(next_row[0]).strip() == ""
                            and all(str(cell).strip() == "" for cell in next_row[:8])
                        ):
                            keterangan += " " + str(next_row[8]) if next_row[8] else ""
                            i += 1
                        else:
                            break
                    # Create data with full keterangan
                    try:
                        data = DistrictCityIndexData(
                            no=row[0],
                            kode=row[1],
                            kabupaten_kota=row[2],
                            jumlah_kecamatan=row[3],
                            jumlah_kelurahan=row[4],
                            jumlah_desa=row[5],
                            luas_wilayah_km2=row[6],
                            jumlah_penduduk=row[7],
                            keterangan=keterangan,
                        )
                        district_city_data.append(data)
                    except (ValueError, IndexError) as e:
                        raise ValueError(f"Failed to parse table row {row}: {e}")
                else:
                    i += 1
            else:
                i += 1

        return pl.DataFrame([data.model_dump() for data in district_city_data])

    def details(self, start_page: int, end_page: int) -> pl.DataFrame:
        """
        Extract district/city index table.

        Args:
            start_page: Starting page number (1-based)
            end_page: Ending page number (1-based, inclusive)

        Returns:
            Polars DataFrame with province district/city data
        """
        # Use specific settings for district/city index tables
        kabupaten_kota_index_settings = {
            "vertical_strategy": "lines",
            "horizontal_strategy": "lines",
            "snap_y_tolerance": 5,
            "intersection_x_tolerance": 10,
        }
        table_rows = self._extract_with_settings(
            start_page,
            end_page,
            kabupaten_kota_index_settings,
            table_format="kabupaten_kota_index",
        )

        # Convert table rows to DistrictCityIndexData objects
        district_city_data = []
        for row in table_rows:
            print(f"Processing row: {row}")
            print(f"Row types: {[type(cell) for cell in row]}")

            if len(row) >= 9:
                # Skip header
                first_cell = str(row[0]).strip() if row[0] else ""

                # Skip if first column is not numeric
                if not (first_cell and first_cell.isdigit()):
                    continue  # Skip header

                try:
                    data = DistrictCityIndexData(
                        no=row[0],
                        kode=row[1],
                        kabupaten_kota=row[2],
                        jumlah_kecamatan=row[3],
                        jumlah_kelurahan=row[4],
                        jumlah_desa=row[5],
                        luas_wilayah_km2=row[6],
                        jumlah_penduduk=row[7],
                        keterangan=row[8],
                    )
                    district_city_data.append(data)
                except (ValueError, IndexError) as e:
                    raise ValueError(f"Failed to parse table row {row}: {e}")

        return pl.DataFrame([data.model_dump() for data in district_city_data])

    def _extract_with_settings(
        self,
        start_page: int,
        end_page: int,
        settings: dict,
        table_format: str = "unknown",
        show_progress: bool = True,
    ) -> List[List[Any]]:
        """
        Extract tables with specific settings.

        Args:
            start_page: Starting page number (1-based)
            end_page: Ending page number (1-based, inclusive)
            settings: Table extraction settings
            table_format: Format of the table being extracted

        Returns:
            List of table rows
        """
        # Temporarily set page range and settings
        original_start = self.start_page
        original_end = self.end_page
        original_settings = self.index_settings
        self.start_page = start_page
        self.end_page = end_page
        self.index_settings = settings

        try:
            tables = self.extract_tables(
                table_format=table_format, show_progress=show_progress
            )
            return tables
        finally:
            # Restore original page range and settings
            self.start_page = original_start
            self.end_page = original_end
            self.index_settings = original_settings


# Example usage
if __name__ == "__main__":
    current_path = os.getcwd()
    script_dir = os.path.dirname(current_path)
    input_dir = os.path.join(script_dir, "datas", "pdf")
    file_name = "aceh_index.pdf"
    pdf_path = os.path.join(input_dir, file_name)

    # Use PDFTableExtractor
    table_extractor = PDFTableExtractor(pdf_path, start_page=1, end_page=5)

    # Extract province index data
    provinsi_index = table_extractor.provinsi_index(start_page=16, end_page=17)
    print(f"Extracted {len(provinsi_index)} rows for provinsi_index")

    # Extract province data
    provinsi = table_extractor.kabupaten_kota_index(start_page=1, end_page=5)
    print(f"Extracted {len(provinsi)} rows for provinsi")
