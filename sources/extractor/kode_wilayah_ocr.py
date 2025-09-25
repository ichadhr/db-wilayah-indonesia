"""
Kode Wilayah OCR Extractor

This module provides OCR-based extraction of kode wilayah data from SNI documents.
It downloads the required images, converts them to PDF, and then performs OCR
to extract structured table data.
"""

import os
import re
from io import StringIO

import polars as pl
from extractor.scrapers.singkatan import download_singkatan_images
from marker.config.parser import ConfigParser
from marker.converters.table import TableConverter
from marker.models import create_model_dict
from marker.output import text_from_rendered
from models.kode_wilayah import KodeWilayah, TableKodeWilayah
from utils.converter import convert_cyrillic_to_latin
from utils.normalize import kode_wilayah
from utils.paths import (
    get_csv_output_path,
    get_datas_dir,
    get_json_output_path,
    get_parquet_output_path,
)

# Constants
SNI_DOC_ID = "SNI_7657-2023"


class KodeWilayahOCR:
    """
    OCR extractor for kode wilayah data from SNI documents.

    This class handles the complete pipeline:
    1. Downloads SNI abbreviation images
    2. Converts images to PDF
    3. Performs OCR on the PDF
    4. Extracts and cleans table data
    5. Saves results in multiple formats
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
        Extract kode wilayah data through the complete OCR pipeline.

        Returns:
            TableKodeWilayah: Extracted and cleaned kode wilayah data
        """
        # Step 1: Download images and create PDF
        print("Downloading SNI abbreviation images...")
        download_singkatan_images()

        # Step 2: Define PDF path
        pdf_path = os.path.join(get_datas_dir(), f"{SNI_DOC_ID}.pdf")

        if not os.path.exists(pdf_path):
            raise FileNotFoundError(
                f"PDF not found at {pdf_path}. Make sure download_singkatan_images() completed successfully."
            )

        # Step 3: Perform OCR on PDF
        # Convert 0-based page range to 1-based for display
        if "-" in self.page_range:
            start, end = self.page_range.split("-")
            display_pages = f"{int(start) + 1}-{int(end) + 1}"
        else:
            display_pages = str(int(self.page_range) + 1)
        print(f"Performing OCR on {pdf_path} (pages {display_pages})...")
        rendered = self.converter(pdf_path)
        text, _, _ = text_from_rendered(rendered)

        # Step 4: Process and clean the extracted table data
        cleaned_records = self._process_table_text(text)

        # Step 5: Save results in multiple formats
        self._save_results(cleaned_records)

        # Step 6: Return structured data
        table = TableKodeWilayah(records=cleaned_records)
        return table

    def _process_table_text(self, text: str) -> list[KodeWilayah]:
        """
        Process raw OCR text and extract cleaned table records.

        Args:
            text: Raw OCR text from PDF

        Returns:
            List of cleaned record dictionaries
        """
        # Clean and parse table markdown
        table_md = "\n".join(
            [
                line
                for line in text.split("\n")
                if not line.startswith("|-----") and line.strip()
            ]
        )
        df = pl.read_csv(StringIO(table_md), separator="|", has_header=True)
        df = df.select([col for col in df.columns if col.strip()])
        columns = df.columns

        # Identify column names
        no_col = next(col for col in columns if "No" in col)
        prov_col = next(col for col in columns if "Provinsi" in col)
        kab_col = next(col for col in columns if "Kabupaten" in col)
        nama_col = next(col for col in columns if "Nama Kota" in col)
        singk_col = next(col for col in columns if "Singkatan" in col)
        parent_col = next(col for col in columns if "Parent" in col)

        # Clean and validate records
        cleaned_records = []

        for record in df.to_dicts():
            # Map column names to expected keys
            record_mapped = {
                'no': record[no_col],
                'provinsi': record[prov_col],
                'kabupaten_kota': record[kab_col],
                'nama_kota': record[nama_col],
                'singkatan_nama_kota': record[singk_col],
                'parent_subdivision': record[parent_col],
            }
            kode_wilayah_obj = kode_wilayah(record_mapped)
            if kode_wilayah_obj:
                cleaned_records.append(kode_wilayah_obj)

        return cleaned_records

    def _save_results(self, records: list[KodeWilayah]) -> None:
        """
        Save extracted data in multiple formats.

        Args:
            records: List of cleaned record dictionaries
        """
        df_clean = pl.DataFrame([r.model_dump() for r in records])

        # Save as Parquet
        df_clean.write_parquet(get_parquet_output_path("kode_wilayah.parquet"))

        # Save as CSV
        df_clean.write_csv(get_csv_output_path("kode_wilayah.csv"))

        # Save as JSON
        df_clean.write_json(get_json_output_path("kode_wilayah.json"))

        print("Kode wilayah data saved successfully in parquet, csv, and json formats.")


# For backward compatibility, if run as script
if __name__ == "__main__":
    extractor = KodeWilayahOCR()
    result = extractor.extract_kode_wilayah()
    print(f"Extracted {len(result.records)} kode wilayah records.")
