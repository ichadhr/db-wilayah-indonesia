import warnings
import re
from typing import List, Optional, Any
from pypdf import PdfReader
from utils.progress import progress_manager
from utils.paths import get_json_output_path
from models.pdf_structure import *

class PDFStructureExtractor:
    # Constants
    PROVINSI_PAGE = "A. Rekapitulasi Kode, Data Wilayah Administrasi Pemerintahan dan Pulau Per Provinsi Seluruh Indonesia"
    PROVINSI_INDEX_PAGE = "B. Rincian Kode dan Data Wilayah Administrasi Pemerintahan Kabupaten/Kota Per Provinsi Seluruh Indonesia"
    KECAMATAN_INDEX_PAGE = "C. Rincian Kode dan Data Wilayah Administrasi Pemerintahan Kecamatan Pada Kabupaten/Kota Per Provinsi Seluruh Indonesia"
    END_SECTION_TEXT = "D.a. Rekapitulasi Jumlah Pulau Per Provinsi Seluruh Indonesia"

    # Pre-compiled regex patterns for performance
    PROVINSI_PATTERN = re.compile(re.escape(PROVINSI_INDEX_PAGE), re.IGNORECASE)
    KECAMATAN_PATTERN = re.compile(re.escape(KECAMATAN_INDEX_PAGE), re.IGNORECASE)
    END_SECTION_PATTERN = re.compile(re.escape(END_SECTION_TEXT), re.IGNORECASE)
    PROVINCE_NAME_PATTERN = re.compile(r"[a-z]+\.\s*Provinsi\s+([^\n]+)", re.IGNORECASE)
    DETAIL_PATTERN = re.compile(r"(C\.[a-z]+\.\d+)\)\s*(.+)", re.IGNORECASE)
    CODE_PATTERN = re.compile(r"(C\.[a-zA-Z]+\.1\))\s*(.+)", re.IGNORECASE)

    def __init__(self, pdf_path: str):
        """
        Initialize the PDF Structure Extractor.
        
        Args:
            pdf_path: Path to the PDF file to extract structure from
        """
        self.pdf_path = pdf_path
        self.reader = PdfReader(pdf_path)

        # Initialize data structures
        self.administrative_structure: List[Province] = []
        self.current_province: Optional[Province] = None
        self.province_data: dict[str, int] = {}  # Use dict for faster lookups
        self.end_section_page: Optional[int] = None
        self.document_index_page: Optional[int] = None
        
        # Track processed provinces to ensure no duplicates
        self.processed_provinces = set()
        
        # Track detail codes to prevent duplicates within a province
        self.current_detail_codes = set()

        # Suppress PDF warnings
        warnings.filterwarnings("ignore", category=UserWarning, module="pypdf")

    def extract_structure(self) -> AdministrativeStructure:
        """
        Extract administrative structure from the PDF file.

        Returns:
            dict: Administrative structure with index, page_range, and provinces
        """
        # Process pages with enhanced rich progress tracking
        with progress_manager.pdf_processing_progress(
            total_pages=len(self.reader.pages),
            table_format="structure_analysis",
            description="Structuring PDF pages"
        ) as progress_ctx:
            for page_num, page in enumerate(self.reader.pages):
                try:
                    self._process_single_page(page, page_num)
                    # Update progress statistics
                    progress_ctx.update_stats(
                        provinces_found=len(self.administrative_structure),
                        kabupaten_kota_count=sum(len(p.details) for p in self.administrative_structure)
                    )
                    progress_ctx.advance(1)
                except Exception as e:
                    print(f"Error processing page {page_num}: {e}")
                    progress_ctx.advance(1)
                    continue

        return self._finalize_structure()

    def _process_single_page(self, page, page_num: int) -> None:
        """
        Process a single page and update the administrative structure.
        
        Args:
            page: PDF page object
            page_num: Zero-based page number
        """
        text = page.extract_text()

        if not text:
            return

        # Check for overall document index page
        if re.search(re.escape(self.PROVINSI_PAGE), text, re.IGNORECASE):
            if self.document_index_page is None:  # Only set once for the first occurrence
                self.document_index_page = page_num
            return

        # Check for provinsi_index_page (province sections)
        if self.PROVINSI_PATTERN.search(text):
            # Extract province name
            match = self.PROVINCE_NAME_PATTERN.search(text)
            if match:
                province_name = match.group(1).strip()
                
                # Ensure we don't process the same province twice
                if province_name not in self.processed_provinces:
                    self.processed_provinces.add(province_name)
                    self.province_data[province_name] = page_num
                    
                    # Reset detail codes tracker for new province
                    self.current_detail_codes = set()

                    # Start building province entry
                    self.current_province = Province(
                        name=province_name,
                        page_range=PageRange(
                            start=page_num + 1,
                            end=None
                        ),
                        sections=ProvinceSections(
                            kabupaten_kota_index=Section(
                                type="B_kabupaten_kota_index",
                                name=f"{province_name} Kabupaten/Kota Index",
                                page_range=PageRange(
                                    start=page_num + 1,
                                    end=None,
                                ),  # Will be updated when kecamatan index page found
                                table_format="kabupaten_kota_index",
                            ),
                            kecamatan_index=Section(
                                type="C_kecamatan_index",
                                name=f"{province_name} Kecamatan Index",
                                page_range=PageRange(
                                    start=None,
                                    end=None,
                                ),  # Both will be updated during processing
                                table_format="kecamatan_index",
                            ),
                        ),
                        total_kota=0,
                        total_kabupaten=0,
                        details=[],
                    )

                    # Append to administrative_structure
                    self.administrative_structure.append(self.current_province)
            return

        # Check for kecamatan_index_page and extract details
        if self.KECAMATAN_PATTERN.search(text) and self.current_province:
            # Update kabupaten_kota_index end based on kecamatan_index_page location
            # Logic: If kabupaten_kota_index start equals kecamatan page + 1 (same page), end = kecamatan page + 1
            # Otherwise, end = kecamatan page
            kabupaten_kota_index_start = self.current_province.sections.kabupaten_kota_index.page_range.start
            if kabupaten_kota_index_start == page_num + 1:
                kabupaten_kota_index_end = page_num + 1
            else:
                kabupaten_kota_index_end = page_num

            self.current_province.sections.kabupaten_kota_index.page_range.end = kabupaten_kota_index_end

            # Update kecamatan_index start to be right after kabupaten_kota_index end
            kecamatan_index_start = kabupaten_kota_index_end + 1
            self.current_province.sections.kecamatan_index.page_range.start = kecamatan_index_start
            return

        # Check for end section - set to last occurrence
        if self.END_SECTION_PATTERN.search(text):
            self.end_section_page = page_num
            return

        # Check for C.*.1) patterns and process details on pages within kecamatan_index range
        if self.current_province:
            kecamatan_index_start = self.current_province.sections.kecamatan_index.page_range.start
            if kecamatan_index_start is not None and page_num >= kecamatan_index_start:
                # Check for C.*.1) patterns to update kecamatan_index end
                kecamatan_index_patterns = self.CODE_PATTERN.findall(text)
                if kecamatan_index_patterns:
                    if kecamatan_index_start == page_num + 1:
                        kecamatan_index_end = page_num + 1
                    else:
                        kecamatan_index_end = page_num
                    self.current_province.sections.kecamatan_index.page_range.end = kecamatan_index_end

                # Process all detail matches (including .2, .3, etc.)
                detail_matches = self.DETAIL_PATTERN.findall(text)
                for code_part, name in detail_matches:
                    code = code_part
                    name = name.strip()

                    # Skip if we've already processed this code in current province
                    if code in self.current_detail_codes:
                        continue

                    self.current_detail_codes.add(code)

                    # Determine region type
                    if name.startswith("Kabupaten"):
                        region_type = "kabupaten"
                    elif name.startswith("Kota"):
                        region_type = "kota"
                    else:
                        region_type = "unknown"

                    # Set start page for this detail
                    detail_start = page_num + 1

                    # Update end page of previous detail if it exists
                    if self.current_province.details:
                        # Set end of previous detail to current page
                        self.current_province.details[-1].page_range.end = page_num

                    detail_entry = Detail(
                        id=code,
                        name=name,
                        page_range=PageRange(
                            start=detail_start,
                            end=None,
                        ),  # End will be updated when next detail found
                        table_format="kabupaten_kota_detail",
                        region_type=region_type,
                    )

                    self.current_province.details.append(detail_entry)

    def _finalize_structure(self) -> AdministrativeStructure:
        """
        Finalize the administrative structure and return the result.
        
        Returns:
            dict: Finalized administrative structure with consistent format
        """
        # Update province end pages
        # Sort provinces by their start page to maintain order
        sorted_provinces = sorted(self.province_data.items(), key=lambda x: x[1])

        for i, (province_name, _) in enumerate(sorted_provinces):
            if i < len(sorted_provinces) - 1:
                # For non-last provinces, end is next province start - 1
                next_start_page = sorted_provinces[i + 1][1]
                end_page = next_start_page - 1
            else:
                # For last province, end is end_section_page - 1
                if self.end_section_page is not None:
                    end_page = self.end_section_page - 1
                else:
                    # Fallback if end_section_text not found
                    end_page = len(self.reader.pages) - 1

            # Find the corresponding province in administrative_structure and update
            for province_info in self.administrative_structure:
                if province_info.name == province_name:
                    province_info.page_range.end = end_page + 1
                    break

        # Set end page of last detail in each province to province end
        for province_info in self.administrative_structure:
            if province_info.details:
                # Set end of last detail to province end
                province_info.details[-1].page_range.end = province_info.page_range.end

        print(
            f"End section found on page: {self.end_section_page + 1 if self.end_section_page else None}"
        )

        # Calculate parent document end as first province start - 1
        parent_end = len(self.reader.pages)
        if self.administrative_structure:
            first_province_start = self.administrative_structure[0].page_range.start
            if first_province_start is not None:
                parent_end = first_province_start - 1

        # Sort administrative structure by start page to ensure consistent order
        self.administrative_structure.sort(key=lambda x: x.page_range.start or 0)

        # Sort details within each province by their id for consistency
        for province_info in self.administrative_structure:
            province_info.details.sort(key=lambda x: int(x.id.split('.')[-1]))

        # Count totals by region_type for validation
        for province_info in self.administrative_structure:
            province_info.total_kabupaten = sum(1 for detail in province_info.details if detail.region_type == "kabupaten")
            province_info.total_kota = sum(1 for detail in province_info.details if detail.region_type == "kota")

        # Wrap in parent structure
        parent_structure = AdministrativeStructure(
            name="Provinsi",
            page_range=PageRange(
                start=self.document_index_page + 1 if self.document_index_page is not None else 1,
                end=parent_end,
            ),
            provinces=self.administrative_structure,
            table_format="provinsi_index"
        )

        return parent_structure

    def validate_structure(self) -> dict[str, Any]:
        """
        Validate the extracted structure for consistency.
        
        Returns:
            dict: Validation report with any issues found
        """
        issues = []
        
        if not self.administrative_structure:
            issues.append("No provinces found in structure")
            return {"valid": False, "issues": issues}
        
        # Check for overlapping page ranges
        for i, province in enumerate(self.administrative_structure):
            # Check province page range validity (skip if end is None)
            province_end = province.page_range.end
            if province_end is not None and province.page_range.start is not None and province.page_range.start >= province_end:
                issues.append(f"Province {province.name}: Invalid page range")

            # Check for overlapping with next province (skip if either end is None)
            if i < len(self.administrative_structure) - 1:
                next_province = self.administrative_structure[i + 1]
                next_start = next_province.page_range.start
                if (province_end is not None and next_start is not None and
                    province_end > next_start):
                    issues.append(
                        f"Overlapping page ranges between {province.name} and {next_province.name}"
                    )

            # Check details within province
            # Sort details by page range for proper overlap detection
            sorted_details = sorted(province.details, key=lambda x: x.page_range.start or 0)

            for j, detail in enumerate(sorted_details):
                # Check detail page range validity (skip if end is None)
                detail_end = detail.page_range.end
                if detail_end is not None and detail.page_range.start is not None and detail.page_range.start > detail_end:
                    issues.append(
                        f"Province {province.name}, Detail {detail.id}: Invalid page range"
                    )

                # Check for overlapping details (skip if either end is None)
                if j < len(sorted_details) - 1:
                    next_detail = sorted_details[j + 1]
                    next_start = next_detail.page_range.start
                    if (detail_end is not None and next_start is not None and
                        detail_end > next_start):
                        issues.append(
                            f"Province {province.name}: Overlapping details {detail.id} and {next_detail.id}"
                        )

        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "province_count": len(self.administrative_structure),
            "total_details": sum(len(p.details) for p in self.administrative_structure)
        }


# usage
if __name__ == "__main__":
    # File
    pdf_path = "datas/Keputusan_Menteri_Dalam_Negeri_Nomor_300.2.2-2138_Tahun_2025.pdf"
    
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
        with open(get_json_output_path("structure_output.json"), "w", encoding="utf-8") as f:
            json.dump(structure, f, ensure_ascii=False, indent=2)
            
    except Exception as e:
        print(f"Error during extraction: {e}")