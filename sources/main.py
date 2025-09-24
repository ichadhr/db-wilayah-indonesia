import os
from extractor.kode_wilayah_ocr import KodeWilayahOCR
from dotenv import load_dotenv
from utils.paths import ensure_output_dirs


def main():
    load_dotenv()

    # Ensure output directories exist
    ensure_output_dirs()

    try:
        # Extract kode wilayah data using OCR
        print("Starting kode wilayah OCR extraction...")
        ocr_extractor = KodeWilayahOCR()
        kode_wilayah_data = ocr_extractor.extract_kode_wilayah()

        print(f"Successfully extracted {len(kode_wilayah_data.records)} kode wilayah records.")
        print("Data saved to output directories (parquet, csv, json).")

    except Exception as e:
        print(f"Error during OCR extraction: {e}")


if __name__ == "__main__":
    main()
