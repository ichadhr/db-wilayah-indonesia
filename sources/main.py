import os
from extractor.pdf_structured_better import PDFStructureExtractor
from extractor.pdf_table import PDFTableExtractor
from models.pdf_table import ProvinceIndexData


def main():
    script_dir = os.path.dirname(__file__)

    # Define output directories
    json_output_dir = os.path.join(script_dir, "output", "json")
    csv_output_dir = os.path.join(script_dir, "output", "csv")

    # Create output directories if they don't exist
    os.makedirs(json_output_dir, exist_ok=True)
    os.makedirs(csv_output_dir, exist_ok=True)

    # Find administrative structure
    pdf_path = os.path.join(script_dir, "datas", "Keputusan_Menteri_Dalam_Negeri_Nomor_300.2.2-2138_Tahun_2025.pdf")

    try:
        extractor = PDFStructureExtractor(pdf_path)
        structure = extractor.extract_structure()
        
        # Validate the structure
        validation = extractor.validate_structure()
        
        if validation["valid"]:
            print(f"\nExtraction successful!")
            print(f"Found {validation['province_count']} provinces")
            print(f"Found {validation['total_details']} total kabupaten/kota")
        else:
            print(f"\nExtraction completed with issues:")
            for issue in validation["issues"]:
                print(f"  - {issue}")
        
        # Optionally save to JSON for inspection
        import json
        structure_json_path = os.path.join(json_output_dir, "structure_output.json")
        with open(structure_json_path, "w", encoding="utf-8") as f:
            json.dump(structure.model_dump(), f, ensure_ascii=False, indent=2)

        # Test PDFTableExtractorChild for provinsi_index using structure page_range
        print("\n--- Testing PDFTableExtractorChild ---")
        try:
            table_extractor = PDFTableExtractor(pdf_path)
            index_name = structure.name
            index_start = structure.page_range.start
            index_end = structure.page_range.end
            index_table_format = structure.table_format

            if index_start is None or index_end is None:
                raise ValueError("Administrative structure page range not properly initialized")
            
            provinsi_index = table_extractor.provinsi_index(start_page=index_start, end_page=index_end)
            print(f"Extracted {len(provinsi_index)} table rows from pages {index_start}-{index_end}")

            # Save table data for inspection using structure format
            table_structure = {
                "name": index_name,
                "page_range": {"start": index_start, "end": index_end},
                "table_format": index_table_format,
                "extracted_data": [data.model_dump() for data in provinsi_index]
            }
            table_json_path = os.path.join(json_output_dir, f"{index_name}_output.json")
            with open(table_json_path, "w", encoding="utf-8") as f:
                json.dump(table_structure, f, ensure_ascii=False, indent=2)
            print(f"Table structure saved to output/json/{index_name}_output.json")

            # Save table data to CSV
            import csv
            table_csv_path = os.path.join(csv_output_dir, f"{index_name}_output.csv")
            with open(table_csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                # Write headers
                if provinsi_index:
                    writer.writerow(ProvinceIndexData.model_fields.keys())
                # Write data rows
                for data in provinsi_index:
                    writer.writerow(data.model_dump().values())
            print(f"Table data saved to output/csv/{index_name}_output.csv")

        except Exception as e:
            print(f"Error during table extraction: {e}")

    except Exception as e:
        print(f"Error during extraction: {e}")


if __name__ == "__main__":
    main()
