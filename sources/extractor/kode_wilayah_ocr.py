"""
Kode Wilayah OCR Extractor

This module provides OCR-based extraction of kode wilayah data from SNI documents.
It downloads the required images, converts them to PDF, and then performs OCR
to extract structured table data.
"""

from marker.converters.table import TableConverter
from marker.config.parser import ConfigParser
from marker.models import create_model_dict
from marker.output import text_from_rendered
import os
import polars as pl
from io import StringIO
import re
from utils.paths import get_datas_dir, get_parquet_output_path, get_csv_output_path, get_json_output_path
from utils.converter import convert_cyrillic_to_latin
from extractor.scrapers.singkatan import download_singkatan_images
from models.kode_wilayah import TableKodeWilayah, KodeWilayah

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
            artifact_dict=create_model_dict()
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
            raise FileNotFoundError(f"PDF not found at {pdf_path}. Make sure download_singkatan_images() completed successfully.")

        # Step 3: Perform OCR on PDF
        print(f"Performing OCR on {pdf_path}...")
        rendered = self.converter(pdf_path)
        text, _, images = text_from_rendered(rendered)

        # Step 4: Process and clean the extracted table data
        cleaned_records = self._process_table_text(text)

        # Step 5: Save results in multiple formats
        self._save_results(cleaned_records)

        # Step 6: Return structured data
        table = TableKodeWilayah(records=[KodeWilayah(**r) for r in cleaned_records])
        return table

    def _process_table_text(self, text: str) -> list[dict]:
        """
        Process raw OCR text and extract cleaned table records.

        Args:
            text: Raw OCR text from PDF

        Returns:
            List of cleaned record dictionaries
        """
        # Clean and parse table markdown
        table_md = '\n'.join([line for line in text.split('\n') if not line.startswith('|-----') and line.strip()])
        df = pl.read_csv(StringIO(table_md), separator='|', has_header=True)
        df = df.select([col for col in df.columns if col.strip()])
        columns = df.columns

        # Identify column names
        no_col = next(col for col in columns if 'No' in col)
        prov_col = next(col for col in columns if 'Provinsi' in col)
        kab_col = next(col for col in columns if 'Kabupaten' in col)
        nama_col = next(col for col in columns if 'Nama Kota' in col)
        singk_col = next(col for col in columns if 'Singkatan' in col)
        parent_col = next(col for col in columns if 'Parent' in col)

        # Clean and validate records
        cleaned_records = []

        for record in df.to_dicts():
    # Apply Cyrillic to Latin conversion to all text fields
            processed_record = {}
            for col_name, value in record.items():
                if isinstance(value, str) and re.search(r'[\u0400-\u04FF]', value):
                    processed_record[col_name] = convert_cyrillic_to_latin(value)
                else:
                    processed_record[col_name] = value
            
            # Clean the 'No' field specifically for number extraction
            no_clean = processed_record[no_col]
            no_str = re.sub(r'\D', '', no_clean)
            if not no_str:
                continue  # Skip invalid records

            no = int(no_str)

            cleaned_records.append({
                'no': no,
                'provinsi': processed_record[prov_col].strip().replace('<br>', ' '),
                'kabupaten_kota': processed_record[kab_col].strip().replace('<br>', ' '),
                'nama_kota': processed_record[nama_col].strip().replace('<br>', ' '),
                'singkatan_nama_kota': processed_record[singk_col].strip().replace('<br>', ' ').upper(),
                'parent_subdivision': processed_record[parent_col].strip().replace('<br>', ' ').upper()
            })

        return cleaned_records

    def _save_results(self, records: list[dict]) -> None:
        """
        Save extracted data in multiple formats.

        Args:
            records: List of cleaned record dictionaries
        """
        df_clean = pl.DataFrame(records)

        # Save as Parquet
        df_clean.write_parquet(get_parquet_output_path('kode_wilayah.parquet'))

        # Save as CSV
        df_clean.write_csv(get_csv_output_path('kode_wilayah.csv'))

        # Save as JSON
        table = TableKodeWilayah(records=[KodeWilayah(**r) for r in records])
        with open(get_json_output_path('kode_wilayah.json'), 'w', encoding='utf-8') as f:
            f.write(table.model_dump_json())

        print("Kode wilayah data saved successfully in parquet, csv, and json formats.")


# For backward compatibility, if run as script
if __name__ == "__main__":
    extractor = KodeWilayahOCR()
    result = extractor.extract_kode_wilayah()
    print(f"Extracted {len(result.records)} kode wilayah records.")