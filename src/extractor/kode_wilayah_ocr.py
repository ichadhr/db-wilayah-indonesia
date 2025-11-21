"""
Kode Wilayah OCR Extractor

Extracts administrative region codes from SNI documents using OCR.
Downloads SNI abbreviation images, converts to PDF, and extracts structured table data.

Pipeline:
1. Download SNI images with intelligent retry logic
2. Convert images to searchable PDF
3. Perform OCR on specified page ranges
4. Extract and clean table data
5. Save results as CSV, JSON, and Parquet files
"""

import logging
import os
from io import StringIO

import polars as pl
from extractor.scrapers.singkatan import download_singkatan_images
from marker.config.parser import ConfigParser
from marker.converters.table import TableConverter
from marker.models import create_model_dict
from marker.output import text_from_rendered
from models.kode_wilayah import KodeWilayah, TableKodeWilayah
from utils.text_utils import kode_wilayah
from utils.paths import (
    get_csv_output_path,
    get_datas_dir,
    get_json_output_path,
    get_parquet_output_path,
    sanitize_folder_file_name,
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

    def extract_kode_wilayah(self, logger=None) -> TableKodeWilayah:
        """
        Execute the complete kode wilayah extraction pipeline.

        Args:
            logger: Optional logger instance for logging progress

        Returns:
            TableKodeWilayah: Structured kode wilayah data

        Raises:
            RuntimeError: If image download fails or PDF is not found
        """
        if logger is None:
            logger = logging.getLogger(__name__)

        # Download and prepare source images
        logger.info("Downloading SNI abbreviation images...")
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
        logger.info(f"Performing OCR on {pdf_path} (pages {display_pages})...")

        rendered = self.converter(pdf_path)
        text, _, _ = text_from_rendered(rendered)

        # Process and clean extracted data
        cleaned_records = self._process_table_text(text)
        self._save_results(cleaned_records, logger)

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

        # Initialize corrector
        from utils.correction import CorrectionLoader
        corrector = CorrectionLoader()

        # Extract and validate records
        cleaned_records = []
        for record in df.to_dicts():
            nama_kota = str(record[column_map["nama_kota"]]).strip()
            singkatan = str(record[column_map["singkatan"]]).strip()
            kabupaten_kota = str(record[column_map["kabupaten"]]).strip()

            # Apply corrections
            # Debug logging
            # print(f"Checking correction for: {repr(nama_kota)}")
            corrected_nama_kota = corrector.get_correction(nama_kota, 'bsni')
            if corrected_nama_kota:
                # print(f"APPLYING CORRECTION: {nama_kota} -> {corrected_nama_kota}")
                meta = corrector.get_metadata(nama_kota, 'bsni')
                nama_kota = corrected_nama_kota
                if meta and meta.get('singkatan'):
                    singkatan = meta.get('singkatan')
                # Also update kabupaten_kota if specified in metadata
                if meta and meta.get('kabupaten_kota'):
                    kabupaten_kota = meta.get('kabupaten_kota')

            mapped_record = {
                "no": record[column_map["no"]],
                "provinsi": record[column_map["provinsi"]],
                "kabupaten_kota": kabupaten_kota,
                "nama_kota": nama_kota,
                "singkatan_nama_kota": singkatan,
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

    def _save_results(self, records: list[KodeWilayah], logger=None) -> None:
        """
        Save extracted kode wilayah data as CSV, JSON, and Parquet files.

        Args:
            records: List of validated KodeWilayah objects
            logger: Optional logger instance for logging progress
        """
        if logger is None:
            logger = logging.getLogger(__name__)

        df_clean = pl.DataFrame([r.model_dump() for r in records])

        # Use sanitized filename base
        filename_base = sanitize_folder_file_name("kode_wilayah")

        # Save CSV
        csv_path = get_csv_output_path(f"{filename_base}.csv", ensure_dir=True)
        df_clean.write_csv(csv_path)
        logger.info(f"Saved {len(records)} kode wilayah records to CSV: {csv_path}")

        # Save JSON
        json_path = get_json_output_path(f"{filename_base}.json", ensure_dir=True)
        df_clean.write_json(json_path)
        logger.info(f"Saved {len(records)} kode wilayah records to JSON: {json_path}")

        # Save Parquet
        parquet_path = get_parquet_output_path(f"{filename_base}.parquet", ensure_dir=True)
        df_clean.write_parquet(parquet_path)
        logger.info(f"Saved {len(records)} kode wilayah records to Parquet: {parquet_path}")


# For backward compatibility, if run as script
if __name__ == "__main__":
    extractor = KodeWilayahOCR()
    result = extractor.extract_kode_wilayah()
    print(f"Extracted {len(result.records)} kode wilayah records.")
