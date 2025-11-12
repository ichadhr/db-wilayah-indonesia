"""
Kode Wilayah OCR Extractor

Extracts administrative region codes from SNI documents using OCR.
Downloads SNI abbreviation images, converts to PDF, and extracts structured table data.

Pipeline:
1. Download SNI images with intelligent retry logic
2. Convert images to searchable PDF
3. Perform OCR on specified page ranges
4. Extract and clean table data
5. Save results as Parquet file
"""

import os
from io import StringIO

import polars as pl
from extractor.scrapers.singkatan import download_singkatan_images
from marker.config.parser import ConfigParser
from marker.converters.table import TableConverter
from marker.models import create_model_dict
from marker.output import text_from_rendered
from models.kode_wilayah import KodeWilayah, TableKodeWilayah
from utils.normalize import kode_wilayah
from utils.paths import (
    get_datas_dir,
    get_parquet_output_path,
)

# Configuration
SNI_DOC_ID = "SNI_7657-2023"


class KodeWilayahOCR:
    """
    OCR-based extractor for Indonesian administrative region codes from SNI documents.

    Handles the complete extraction pipeline from image download to structured data output.
    Uses intelligent retry logic for robust image downloading and Marker library for OCR.
    """

    def __init__(self, page_range: str = "10-24"):
        """
        Initialize the OCR extractor.

        Args:
            page_range: Page range to process (default: "10-24")
        """
        self.page_range = page_range
        self.schema = TableKodeWilayah.model_json_schema()
        self.config = {
            "disable_image_extraction": True,
            "force_ocr": True,
            "strip_existing_ocr": True,
            "page_range": page_range,
        }
        self.config_parser = ConfigParser(self.config)
        self.converter = TableConverter(
            config=self.config_parser.generate_config_dict(),
            artifact_dict=create_model_dict(),
        )

    def extract_kode_wilayah(self) -> TableKodeWilayah:
        """
        Execute the complete kode wilayah extraction pipeline.

        Returns:
            TableKodeWilayah: Structured kode wilayah data

        Raises:
            RuntimeError: If image download fails or PDF is not found
        """
        # Download and prepare source images
        print("Downloading SNI abbreviation images...")
        success, failed_images = download_singkatan_images()
        if not success:
            raise RuntimeError(
                f"Failed to download SNI images. Failed images: {', '.join(failed_images)}. "
                "Cannot proceed with OCR extraction."
            )

        # Verify PDF exists
        pdf_path = os.path.join(get_datas_dir(), f"{SNI_DOC_ID}.pdf")
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(
                f"PDF not found at {pdf_path}. Download process may have failed."
            )

        # Perform OCR extraction
        display_pages = self._format_page_range_for_display()
        print(f"Performing OCR on {pdf_path} (pages {display_pages})...")

        rendered = self.converter(pdf_path)
        text, _, _ = text_from_rendered(rendered)

        # Process and clean extracted data
        cleaned_records = self._process_table_text(text)
        self._save_results(cleaned_records)

        return TableKodeWilayah(records=cleaned_records)

    def _format_page_range_for_display(self) -> str:
        """Convert 0-based page range to 1-based for user display."""
        if "-" in self.page_range:
            start, end = self.page_range.split("-")
            return f"{int(start) + 1}-{int(end) + 1}"
        else:
            return str(int(self.page_range) + 1)

    def _process_table_text(self, text: str) -> list[KodeWilayah]:
        """
        Process raw OCR text and extract cleaned kode wilayah records.

        Args:
            text: Raw OCR text from PDF containing table data

        Returns:
            List of validated KodeWilayah objects
        """
        # Clean table markdown by removing separator lines
        table_lines = [
            line for line in text.split("\n")
            if not line.startswith("|-----") and line.strip()
        ]
        table_md = "\n".join(table_lines)

        # Parse table into DataFrame
        df = pl.read_csv(StringIO(table_md), separator="|", has_header=True)
        df = df.select([col for col in df.columns if col.strip()])

        # Identify columns by content patterns
        column_map = self._identify_table_columns(df.columns)

        # Extract and validate records
        cleaned_records = []
        for record in df.to_dicts():
            mapped_record = {
                "no": record[column_map["no"]],
                "provinsi": record[column_map["provinsi"]],
                "kabupaten_kota": record[column_map["kabupaten"]],
                "nama_kota": record[column_map["nama_kota"]],
                "singkatan_nama_kota": record[column_map["singkatan"]],
                "parent_subdivision": record[column_map["parent"]],
            }

            kode_wilayah_obj = kode_wilayah(mapped_record)
            if kode_wilayah_obj:
                cleaned_records.append(kode_wilayah_obj)

        return cleaned_records

    def _identify_table_columns(self, columns: list[str]) -> dict[str, str]:
        """
        Identify table columns by matching against expected patterns.

        Args:
            columns: List of column names from OCR

        Returns:
            Dict mapping expected column types to actual column names
        """
        return {
            "no": next(col for col in columns if "No" in col),
            "provinsi": next(col for col in columns if "Provinsi" in col),
            "kabupaten": next(col for col in columns if "Kabupaten" in col),
            "nama_kota": next(col for col in columns if "Nama Kota" in col),
            "singkatan": next(col for col in columns if "Singkatan" in col),
            "parent": next(col for col in columns if "Parent" in col),
        }

    def _save_results(self, records: list[KodeWilayah]) -> None:
        """
        Save extracted kode wilayah data as Parquet file.

        Args:
            records: List of validated KodeWilayah objects
        """
        df_clean = pl.DataFrame([r.model_dump() for r in records])
        df_clean.write_parquet(get_parquet_output_path("kode_wilayah.parquet"))

        print(f"Kode wilayah data saved successfully: {len(records)} records in parquet format.")


# For backward compatibility, if run as script
if __name__ == "__main__":
    extractor = KodeWilayahOCR()
    result = extractor.extract_kode_wilayah()
    print(f"Extracted {len(result.records)} kode wilayah records.")
