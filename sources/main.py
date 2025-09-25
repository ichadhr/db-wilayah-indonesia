import json
import os

from dotenv import load_dotenv
from extractor.kode_wilayah_ocr import KodeWilayahOCR
from extractor.pdf_structure import PDFStructureExtractor
from extractor.pdf_table import PDFTableExtractor
from utils.paths import (ensure_output_dirs, get_csv_output_path, get_json_output_path, get_parquet_output_path, get_pdf_path, sanitize_filename)
from utils.structure_utils import (kabupaten_kota_detail, kabupaten_kota_index, kecamatan_index, provinsi)


def main():
    load_dotenv()

    MAIN_PDF = os.getenv("MAIN_PDF") or ""
    # Find administrative structure
    pdf_path = get_pdf_path(MAIN_PDF)

    # Ensure output directories exist
    ensure_output_dirs()

    structure_json_path = extract_structure(pdf_path)
    if not structure_json_path:
        raise ValueError("Failed to extract structure")

    try:
        # Get province index page ranges using utility
        prov_df = provinsi(structure_json_path)
        if len(prov_df) == 0:
            raise ValueError("No province index found in structure")

        prov_row = prov_df.row(0)
        index_start = prov_row[2]  # start_page column
        index_end = prov_row[3]  # end_page column
        index_name = prov_row[0]  # name column
        index_table_format = prov_row[1]  # table_format column

        table_extractor = PDFTableExtractor(pdf_path)
        provinsi_index = table_extractor.provinsi_index(
            start_page=index_start, end_page=index_end
        )
        print(f"Validation: Raw table records extracted and filtered to valid province entries")
        print(
            f"Extracted {len(provinsi_index)} table rows from pages {index_start}-{index_end}"
        )

        # Save table data using Polars native methods
        output_base = sanitize_filename(index_name)

        # CSV (tabular data)
        csv_path = get_csv_output_path(f"{output_base}.csv")
        provinsi_index.write_csv(csv_path)
        print(f"Table data saved to {csv_path}")

        # Parquet (efficient storage)
        parquet_path = get_parquet_output_path(f"{output_base}.parquet")
        provinsi_index.write_parquet(parquet_path)
        print(f"Table data saved to {parquet_path}")

        # JSON (DataFrame data only)
        json_path = get_json_output_path(f"{output_base}.json")
        provinsi_index.write_json(json_path)
        print(f"Table data saved to {json_path}")

        # Debug JSON (metadata + sample data) in debug folder
        debug_data = {
            "name": index_name,
            "page_range": {"start": index_start, "end": index_end},
            "table_format": index_table_format,
            "row_count": len(provinsi_index),
            "columns": provinsi_index.columns,
            "sample_data": provinsi_index.head(3).to_dicts(),
        }
        debug_path = get_json_output_path(os.path.join("debug", f"{output_base}.json"))
        with open(debug_path, "w", encoding="utf-8") as f:
            json.dump(debug_data, f, ensure_ascii=False, indent=2)
        print(f"Debug info saved to {debug_path}")

    except Exception as e:
        print(f"Error during provinsi table extraction: {e}")


def extract_structure(doc_path):
    try:
        print("Starting scanning PDF document...")
        extractor = PDFStructureExtractor(doc_path)
        structure = extractor.extract_structure()

        # Validate the structure
        print("Validating structure...")
        validation = extractor.validate_structure()

        if validation["valid"]:
            print(f"\nExtraction successful!")
            print(f"Found {validation['province_count']} provinces")
            print(f"Found {validation['total_details']} total kabupaten/kota")
        else:
            print(f"\nExtraction completed with issues:")
            for issue in validation["issues"]:
                print(f"  - {issue}")

        # Outputs as JSON
        structure_json_path = get_json_output_path("structure_pdf.json")
        with open(structure_json_path, "w", encoding="utf-8") as f:
            json.dump(structure.model_dump(), f, ensure_ascii=False, indent=2)
        print(f"Successfully structured PDF document {structure_json_path}.")

        return structure_json_path

    except Exception as e:
        print(f"Error during get PDF structure: {e}")


def extract_code_wilayah():
    try:
        # Extract kode wilayah data using OCR
        print("Starting kode wilayah OCR extraction...")
        ocr_extractor = KodeWilayahOCR()
        kode_wilayah_data = ocr_extractor.extract_kode_wilayah()

        print(
            f"Successfully extracted {len(kode_wilayah_data.records)} kode wilayah records."
        )
        print("Data saved to output directories (parquet, csv, json).")
    except Exception as e:
        print(f"Error during OCR extraction: {e}")


if __name__ == "__main__":
    main()
