import os
import re
from typing import Any, List, Optional

import pdfplumber
import polars as pl

from models.pdf_table import (
    DetailsData,
    DistrictIndexData,
    ProvinceIndexData,
    RegencyIndexData,
)
from utils.errors import (
    FileOperationError,
    TableExtractionError,
    error_handler,
    log_error,
)
from utils.progress import progress_manager
from utils.text_utils import (
    clean_leading_number,
    normalize_ibukota_kabupaten_kota,
    normalize_kabupaten_kota,
)


@error_handler(operation_name="get_p_bsni_mapping", log_errors=True)
def get_p_bsni_mapping() -> dict[str, str]:
    """
    Load province name to abbreviation mapping from kode_wilayah.parquet file.

    Returns:
        Dictionary mapping province names to their ISO abbreviations (with ID- prefix)
    """
    parquet_path = os.path.join(
        os.path.dirname(__file__), "..", "output", "parquet", "kode_wilayah.parquet"
    )
    try:
        df = pl.read_parquet(parquet_path)
    except Exception as e:
        raise FileOperationError(
            f"Failed to read kode_wilayah.parquet for province BSNI mapping: {str(e)}",
            file_path=parquet_path,
            operation="read_parquet",
        ) from e
    mapping = {}
    for row in df.to_dicts():
        provinsi = row["provinsi"]
        parent_subdivision = row["parent_subdivision"]
        # Keep the full ID-XX format
        if parent_subdivision:
            mapping[provinsi] = parent_subdivision
    return mapping


@error_handler(operation_name="get_k_bsni_mapping", log_errors=True)
def get_k_bsni_mapping() -> dict[str, str]:
    """
    Load ibukota_kabupaten_kota to singkatan_nama_kota mapping from kode_wilayah.parquet file.

    Returns:
        Dictionary mapping normalized ibukota_kabupaten_kota names to singkatan_nama_kota
    """
    parquet_path = os.path.join(
        os.path.dirname(__file__), "..", "output", "parquet", "kode_wilayah.parquet"
    )
    try:
        df = pl.read_parquet(parquet_path)
    except Exception as e:
        raise FileOperationError(
            f"Failed to read kode_wilayah.parquet for kecamatan BSNI mapping: {str(e)}",
            file_path=parquet_path,
            operation="read_parquet",
        ) from e
    mapping = {}
    for row in df.to_dicts():
        nama_kota = row["nama_kota"]
        singkatan = row["singkatan_nama_kota"]
        if nama_kota and singkatan:
            # Normalize the key: remove "Kota " prefix, spaces and convert to lowercase
            normalized_key = (
                re.sub(r"^Kota\s+", "", nama_kota, flags=re.IGNORECASE)
                .replace(" ", "")
                .lower()
            )
            mapping[normalized_key] = singkatan
    return mapping


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
            show_progress: Whether to display progress bar during extraction

        Returns:
            List of table rows with duplicate headers merged
        """
        records = []
        try:
            pdf = pdfplumber.open(self.pdf_path)
        except Exception as e:
            raise FileOperationError(
                f"Failed to open PDF file: {str(e)}",
                file_path=self.pdf_path,
                operation="pdf_open",
            ) from e
        with pdf:
            if pdf.pages:
                end_page = (
                    self.end_page if self.end_page is not None else len(pdf.pages)
                )
                total_pages = min(end_page, len(pdf.pages)) - (self.start_page - 1)

                if show_progress:
                    with progress_manager.table_extraction_progress(
                        total_pages=total_pages,
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
        return PDFTableExtractorBase._merge_headers(records)

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

    @staticmethod
    def _merge_headers(merged_rows: List[List[Any]]) -> List[List[Any]]:
        """
        Merge table data by removing duplicate header blocks from multipage extractions.

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

    @error_handler(operation_name="provinsi_index_extraction", log_errors=True)
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
                        p_bsni="",  # Will be filled by DataFrame operations
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
                    raise TableExtractionError(
                        f"Failed to parse province index table row {row}: {str(e)}",
                        table_format="provinsi_index",
                    ) from e

        # DataFrame-based matching for p_bsni
        df_province = pl.DataFrame([data.model_dump() for data in province_index_data])

        # Filter provinces that have provinsi name (not empty)
        provinces_with_name = df_province.filter(pl.col("provinsi") != "")

        # Deduplicate provinces to avoid duplicates in join (PDF may have repeated rows)
        provinces_with_name = provinces_with_name.unique(subset=["provinsi"])

        if len(provinces_with_name) > 0:
            # Load kode_wilayah DataFrame
            kode_wilayah_path = os.path.join(
                os.path.dirname(__file__),
                "..",
                "output",
                "parquet",
                "kode_wilayah.parquet",
            )
            try:
                df_kode_wilayah = pl.read_parquet(kode_wilayah_path)
            except Exception as e:
                raise FileOperationError(
                    f"Failed to read kode_wilayah.parquet for province mapping: {str(e)}",
                    file_path=kode_wilayah_path,
                    operation="read_parquet",
                ) from e

            # Perform join on provinsi name
            joined = provinces_with_name.join(
                df_kode_wilayah, left_on="provinsi", right_on="provinsi", how="left"
            )

            # Update p_bsni field and identify unmatched
            matched = joined.filter(pl.col("parent_subdivision").is_not_null())
            unmatched = joined.filter(pl.col("parent_subdivision").is_null())

            # Collect unmatched province names
            unmatched_provinces = []
            for row in unmatched.iter_rows(named=True):
                unmatched_provinces.append(row["provinsi"])

            # Log unmatched provinces (PDF entries not in BSNI)
            if unmatched_provinces:
                log_path = os.path.join(
                    os.path.dirname(__file__),
                    "..",
                    "output",
                    "log",
                    "p_bsni_mismatch_pdf.log",
                )
                os.makedirs(os.path.dirname(log_path), exist_ok=True)
                with open(log_path, "a", encoding="utf-8") as f:
                    f.write(
                        f"Province extraction - {len(unmatched_provinces)} provinces from PDF not found in BSNI:\n"
                    )
                    f.write("Format: province\n\n")
                    for name in unmatched_provinces:
                        f.write(f"  - {name}\n")
                    f.write("\n")

            # Log unmapped BSNI provinces (BSNI entries not referenced by PDF)
            # Get unique provinces from PDF
            pdf_provinces = set(
                provinces_with_name.select("provinsi").to_series().to_list()
            )

            # Get unique provinces from BSNI
            bsni_provinces_df = df_kode_wilayah.select(
                "provinsi", "parent_subdivision"
            ).unique()
            bsni_provinces = set(
                bsni_provinces_df.select("provinsi").to_series().to_list()
            )

            # Find BSNI provinces not in PDF
            unmapped_bsni_provinces = bsni_provinces - pdf_provinces

            if unmapped_bsni_provinces:
                log_path = os.path.join(
                    os.path.dirname(__file__),
                    "..",
                    "output",
                    "log",
                    "p_bsni_mismatch_ocr.log",
                )
                os.makedirs(os.path.dirname(log_path), exist_ok=True)
                with open(log_path, "a", encoding="utf-8") as f:
                    f.write(
                        f"Province extraction - {len(unmapped_bsni_provinces)} BSNI provinces not referenced by PDF:\n"
                    )
                    f.write("Format: province | singkatan\n\n")
                    # Get singkatan for each unmapped province
                    for prov in sorted(unmapped_bsni_provinces):
                        singkatan_row = bsni_provinces_df.filter(
                            pl.col("provinsi") == prov
                        )
                        singkatan = (
                            singkatan_row.select("parent_subdivision").to_series()[0]
                            if len(singkatan_row) > 0
                            else "-"
                        )
                        f.write(f"  - {prov} | {singkatan}\n")
                    f.write("\n")

            # Update the original dataframe with matched p_bsni values
            if len(matched) > 0:
                matched_updates = matched.select(["provinsi", "parent_subdivision"])
                df_province = (
                    df_province.join(matched_updates, on="provinsi", how="left")
                    .with_columns(
                        p_bsni=pl.when(pl.col("parent_subdivision").is_not_null())
                        .then(pl.col("parent_subdivision"))
                        .otherwise(pl.col("p_bsni"))
                    )
                    .drop("parent_subdivision")
                )

        # Deduplicate final dataframe to remove any remaining duplicates
        df_province = df_province.unique(subset=["provinsi"])

        return df_province

    @error_handler(operation_name="kabupaten_kota_index_extraction", log_errors=True)
    def kabupaten_kota_index(
        self, start_page: int, end_page: int, show_progress: bool = True
    ) -> pl.DataFrame:
        """
        Extract regency index table.

        Args:
            start_page: Starting page number (1-based)
            end_page: Ending page number (1-based, inclusive)
            show_progress: Whether to display progress bar during extraction

        Returns:
            Polars DataFrame with province regency data
        """
        # Use specific settings for regency index tables
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

        # Convert table rows to RegencyIndexData objects
        regency_index_data = []
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
                        data = RegencyIndexData(
                            no=row[0],
                            kode_kabupaten_kota=row[1],
                            kabupaten_kota=row[2],
                            jumlah_kecamatan=row[3],
                            jumlah_kelurahan=row[4],
                            jumlah_desa=row[5],
                            luas_wilayah_km2=row[6],
                            jumlah_penduduk=row[7],
                            keterangan=keterangan,
                        )
                        regency_index_data.append(data)
                    except (ValueError, IndexError) as e:
                        raise TableExtractionError(
                            f"Failed to parse kabupaten_kota index table row {row}: {str(e)}",
                            table_format="kabupaten_kota_index",
                        ) from e
                else:
                    i += 1
            else:
                i += 1

        return pl.DataFrame([data.model_dump() for data in regency_index_data])

    @error_handler(operation_name="kecamatan_index_extraction", log_errors=True)
    def kecamatan_index(
        self, start_page: int, end_page: int, show_progress: bool = True
    ) -> tuple[pl.DataFrame, list, list]:
        """
        Extract district index table.

        Args:
            start_page: Starting page number (1-based)
            end_page: Ending page number (1-based, inclusive)
            show_progress: Whether to display progress bar during extraction

        Returns:
            Tuple of (Polars DataFrame with district data,
                      list of unmatched ibukota names from PDF,
                      list of unmapped BSNI cities)
        """
        # Use specific settings for district index tables
        kecamatan_index_settings = {}  # empty config
        table_rows = self._extract_with_settings(
            start_page,
            end_page,
            kecamatan_index_settings,
            table_format="kecamatan_index",
            show_progress=show_progress,
        )

        district_index_data = []
        unmatched_names = []  # list of (ibukota_name, kode_kecamatan)
        unmapped_bsni = []  # list of unmapped BSNI cities

        # Context variables for hierarchical data
        current_province = {
            "no": "",  # Province Roman numeral
            "kode_provinsi": "",
            "provinsi": "",
            "ibukota_provinsi": "",
            "jumlah_kabupaten": 0,
            "jumlah_kota": 0,
        }
        current_regency = {
            "kabupaten_kota": "",
            "ibukota_kabupaten_kota": "",
            "jumlah_kecamatan": 0,
            "jumlah_kelurahan": 0,
            "jumlah_desa": 0,
        }

        # Helper for safe row access (avoid shadowing)
        def safe_row_val(row_data: List[Any], idx: int, default: Any = "") -> Any:
            return (
                row_data[idx]
                if len(row_data) > idx and row_data[idx] is not None
                else default
            )

        for row in table_rows:
            if not row or len(row) < 10:
                continue

            first_cell = safe_row_val(row, 0, "").strip()
            kode = safe_row_val(row, 1, "").strip()

            # CHECK FOR HISTORICAL DISTRICTS FIRST - BEFORE header skip!
            district_name = safe_row_val(row, 2, "").strip()
            if (
                kode == ""
                and first_cell == ""
                and district_name
                and not district_name.isdigit()
                and district_name not in ["KAB", "KOTA", "KEC"]
            ):
                # Only process real historical districts with meaningful names
                keterangan_text = safe_row_val(row, 11, "")

                data = DistrictIndexData(
                    no=current_province["no"],  # Inherit province Roman numeral
                    kode_provinsi=current_province["kode_provinsi"],
                    provinsi=current_province["provinsi"],
                    ibukota_provinsi=current_province["ibukota_provinsi"],
                    kode_kabupaten_kota="",
                    kabupaten_kota="",
                    ibukota_kabupaten_kota="",
                    kode_kecamatan="",
                    kecamatan=district_name,
                    k_bsni="",
                    jumlah_kabupaten=0,
                    jumlah_kota=0,
                    jumlah_kecamatan=0,
                    jumlah_kelurahan=0,
                    jumlah_desa=0,
                    luas_wilayah_km2=0.0,
                    jumlah_penduduk=0,
                    keterangan=keterangan_text,
                )

                district_index_data.append(data)
                continue

            # Skip headers - AFTER checking for historical districts
            if (
                first_cell == "NO"
                or (first_cell == "" and kode == "")
                or (safe_row_val(row, 4) == "KAB" and safe_row_val(row, 5) == "KOTA")
            ):
                continue

            # Parse codes
            kode_parts = kode.split(".") if kode else []
            if len(kode_parts) < 1:
                continue

            kode_provinsi = kode_parts[0]
            kode_kabupaten_kota = (
                f"{kode_parts[0]}.{kode_parts[1]}" if len(kode_parts) > 1 else ""
            )
            kode_kecamatan = kode if len(kode_parts) == 3 else ""

            if len(kode_parts) == 1:  # Province
                # Update context FIRST
                current_province.update(
                    {
                        "no": first_cell,  # Store Roman numeral for inheritance
                        "kode_provinsi": kode_provinsi,
                        "provinsi": safe_row_val(row, 2, ""),
                        "ibukota_provinsi": safe_row_val(row, 3, ""),
                        "jumlah_kabupaten": safe_row_val(row, 4, 0),
                        "jumlah_kota": safe_row_val(row, 5, 0),
                    }
                )

                # Use current row values directly for province data (not empty context)
                data = DistrictIndexData(
                    no=first_cell,
                    kode_provinsi=kode_provinsi,
                    provinsi=safe_row_val(row, 2, ""),  # Direct from row
                    ibukota_provinsi=safe_row_val(row, 3, ""),  # Direct from row
                    kode_kabupaten_kota="",
                    kabupaten_kota="",
                    ibukota_kabupaten_kota="",
                    kode_kecamatan="",
                    kecamatan="",
                    k_bsni="",
                    jumlah_kabupaten=safe_row_val(row, 4, 0),
                    jumlah_kota=safe_row_val(row, 5, 0),
                    jumlah_kecamatan=safe_row_val(row, 6, 0),
                    jumlah_kelurahan=safe_row_val(row, 7, 0),
                    jumlah_desa=safe_row_val(row, 8, 0),
                    luas_wilayah_km2=safe_row_val(row, 9, 0.0),
                    jumlah_penduduk=safe_row_val(row, 10, 0),
                    keterangan=safe_row_val(row, 11, ""),
                )

                district_index_data.append(data)

            elif len(kode_parts) == 2:  # Regency
                current_regency.update(
                    {
                        "kabupaten_kota": safe_row_val(row, 2, ""),
                        "ibukota_kabupaten_kota": safe_row_val(row, 3, ""),
                        "jumlah_kecamatan": safe_row_val(row, 6, 0),
                        "jumlah_kelurahan": safe_row_val(row, 7, 0),
                        "jumlah_desa": safe_row_val(row, 8, 0),
                    }
                )

                # Common base data for regency/district
                base_data = {
                    "kode_provinsi": kode_provinsi,
                    "provinsi": current_province["provinsi"],
                    "ibukota_provinsi": current_province["ibukota_provinsi"],
                    "luas_wilayah_km2": safe_row_val(row, 9, 0.0),
                    "jumlah_penduduk": safe_row_val(row, 10, 0),
                    "keterangan": safe_row_val(row, 11, ""),
                }

                data = DistrictIndexData(
                    no=current_province["no"],  # Inherit province Roman numeral
                    **base_data,
                    kode_kabupaten_kota=kode_kabupaten_kota,
                    kabupaten_kota=safe_row_val(row, 2, ""),
                    ibukota_kabupaten_kota=safe_row_val(row, 3, ""),
                    kode_kecamatan="",
                    kecamatan="",
                    k_bsni="",
                    jumlah_kabupaten=0,
                    jumlah_kota=0,  # Regency has 0 for these
                    jumlah_kecamatan=safe_row_val(row, 6, 0),
                    jumlah_kelurahan=safe_row_val(row, 7, 0),
                    jumlah_desa=safe_row_val(row, 8, 0),
                )

                district_index_data.append(data)

            elif len(kode_parts) == 3:  # District
                # Common base data for district
                base_data = {
                    "kode_provinsi": kode_provinsi,
                    "provinsi": current_province["provinsi"],
                    "ibukota_provinsi": current_province["ibukota_provinsi"],
                    "luas_wilayah_km2": safe_row_val(row, 9, 0.0),
                    "jumlah_penduduk": safe_row_val(row, 10, 0),
                    "keterangan": safe_row_val(row, 11, ""),
                }

                # Temporarily set k_bsni to empty - will be filled by DataFrame operations
                k_bsni_value = ""

                data = DistrictIndexData(
                    no=current_province["no"],  # Inherit province Roman numeral
                    **base_data,
                    kode_kabupaten_kota=kode_kabupaten_kota,
                    kabupaten_kota=current_regency["kabupaten_kota"],
                    ibukota_kabupaten_kota=current_regency["ibukota_kabupaten_kota"],
                    kode_kecamatan=kode_kecamatan,
                    kecamatan=safe_row_val(row, 2, ""),
                    k_bsni=k_bsni_value,
                    jumlah_kabupaten=0,
                    jumlah_kota=0,
                    jumlah_kecamatan=0,  # District has 0 for these
                    jumlah_kelurahan=safe_row_val(row, 7, 0),
                    jumlah_desa=safe_row_val(row, 8, 0),
                )

                district_index_data.append(data)

        # DataFrame-based matching for k_bsni
        df_district = pl.DataFrame([data.model_dump() for data in district_index_data])

        # Filter districts that have ibukota_kabupaten_kota (not empty)
        districts_with_ibukota = df_district.filter(
            (pl.col("ibukota_kabupaten_kota") != "") & (pl.col("kode_kecamatan") != "")
        )

        if len(districts_with_ibukota) > 0:
            # Load kode_wilayah DataFrame
            kode_wilayah_path = os.path.join(
                os.path.dirname(__file__),
                "..",
                "output",
                "parquet",
                "kode_wilayah.parquet",
            )
            try:
                df_kode_wilayah = pl.read_parquet(kode_wilayah_path)
            except Exception as e:
                raise FileOperationError(
                    f"Failed to read kode_wilayah.parquet for kecamatan mapping: {str(e)}",
                    file_path=kode_wilayah_path,
                    operation="read_parquet",
                ) from e

            # Prepare kode_wilayah for join - create normalized key
            df_kode_wilayah_join = df_kode_wilayah.with_columns(
                join_key=pl.struct(["kabupaten_kota", "nama_kota"]).map_elements(
                    lambda x: (
                        clean_leading_number(
                            normalize_kabupaten_kota(x["kabupaten_kota"] or "")
                        )
                        .replace(" ", "")
                        .lower()
                        + clean_leading_number(
                            re.sub(
                                r"^Kota\s+",
                                "",
                                normalize_ibukota_kabupaten_kota(x["nama_kota"] or ""),
                                flags=re.IGNORECASE,
                            )
                        )
                        .replace(" ", "")
                        .lower()
                    ),
                    return_dtype=pl.Utf8,
                )
            )

            # Prepare districts for join
            districts_join = districts_with_ibukota

            # Apply corrections to normalized_ibukota using BSNICorrection
            from pipeline.corrections.bsni import BSNICorrection

            corrector = BSNICorrection()

            def apply_kecamatan_correction(struct_val):
                val = struct_val["ibukota"]
                kab_kota = struct_val["kabupaten"]

                if not val:
                    return val

                corrected = corrector.get_correction(val, "kecamatan_index")
                if corrected:
                    # Check metadata for scope constraints
                    meta = corrector.get_metadata(val, "kecamatan_index")
                    if meta:
                        target_kab = meta.get("kabupaten_kota")
                        # If target_kab is defined, it MUST match the current kabupaten_kota
                        # We normalize both for comparison to be safe
                        if target_kab:
                            norm_target = (
                                normalize_kabupaten_kota(
                                    clean_leading_number(target_kab)
                                )
                                .replace(" ", "")
                                .lower()
                            )
                            norm_current = (
                                normalize_kabupaten_kota(
                                    clean_leading_number(kab_kota or "")
                                )
                                .replace(" ", "")
                                .lower()
                            )
                            if norm_target != norm_current:
                                return val  # Skip correction if context doesn't match
                    return corrected
                else:
                    return val

            districts_join = districts_join.with_columns(
                ibukota_kabupaten_kota=pl.struct(
                    [
                        pl.col("ibukota_kabupaten_kota").alias("ibukota"),
                        pl.col("kabupaten_kota").alias("kabupaten"),
                    ]
                ).map_elements(apply_kecamatan_correction, return_dtype=pl.Utf8)
            ).with_columns(
                # Calculate join_key after correction
                join_key=pl.struct(
                    ["kabupaten_kota", "ibukota_kabupaten_kota"]
                ).map_elements(
                    lambda x: (
                        clean_leading_number(
                            normalize_kabupaten_kota(x["kabupaten_kota"] or "")
                        )
                        .replace(" ", "")
                        .lower()
                        + clean_leading_number(
                            re.sub(
                                r"^Kota\s+",
                                "",
                                normalize_ibukota_kabupaten_kota(
                                    x["ibukota_kabupaten_kota"] or ""
                                ),
                                flags=re.IGNORECASE,
                            )
                        )
                        .replace(" ", "")
                        .lower()
                    ),
                    return_dtype=pl.Utf8,
                )
            )

            # Perform join
            joined = districts_join.join(
                df_kode_wilayah_join, on="join_key", how="left"
            )

            # Update k_bsni field and identify unmatched
            matched = joined.filter(pl.col("singkatan_nama_kota").is_not_null())
            unmatched = joined.filter(pl.col("singkatan_nama_kota").is_null())

            # Collect unmatched names (PDF entries that didn't match BSNI)
            for row in unmatched.iter_rows(named=True):
                expanded_name = normalize_ibukota_kabupaten_kota(
                    row["ibukota_kabupaten_kota"]
                )
                unmatched_names.append((expanded_name, row["kabupaten_kota"]))

            # Update the original dataframe with matched k_bsni values AND corrected ibukota
            if len(matched) > 0:
                # We want to update 'k_bsni' AND 'ibukota_kabupaten_kota'
                # The 'matched' dataframe comes from 'joined', which has the CORRECTED 'ibukota_kabupaten_kota'
                # So we select it from there.
                matched_updates = matched.select(
                    ["kode_kecamatan", "singkatan_nama_kota", "ibukota_kabupaten_kota"]
                )

                df_district = (
                    df_district.join(matched_updates, on="kode_kecamatan", how="left")
                    .with_columns(
                        k_bsni=pl.when(pl.col("singkatan_nama_kota").is_not_null())
                        .then(pl.col("singkatan_nama_kota"))
                        .otherwise(pl.col("k_bsni")),
                        # Update ibukota_kabupaten_kota if we found a match (which implies we might have corrected it)
                        # Note: matched_updates has column "ibukota_kabupaten_kota" (the corrected one)
                        # We need to disambiguate because join might create suffix
                        ibukota_kabupaten_kota=pl.when(
                            pl.col("singkatan_nama_kota").is_not_null()
                        )
                        .then(pl.col("ibukota_kabupaten_kota_right"))
                        .otherwise(pl.col("ibukota_kabupaten_kota")),
                    )
                    .drop(["singkatan_nama_kota", "ibukota_kabupaten_kota_right"])
                )

            # Identify unmapped BSNI records using anti-join
            # Find BSNI cities in this province that are NOT used by any district
            unmapped_bsni = []
            if len(districts_with_ibukota) > 0:
                # Get current province name
                current_province = (
                    districts_with_ibukota.select("provinsi").unique().to_series()[0]
                )

                # Filter BSNI to current province only
                province_bsni = df_kode_wilayah.filter(
                    pl.col("provinsi") == current_province
                )

                # Get unique k_bsni codes that were actually used
                used_bsni = (
                    df_district.filter(pl.col("k_bsni").is_not_null())
                    .select("k_bsni")
                    .unique()
                )

                # Anti-join: find BSNI codes NOT in used k_bsni
                unmapped_bsni_df = province_bsni.join(
                    used_bsni,
                    left_on="singkatan_nama_kota",
                    right_on="k_bsni",
                    how="anti",
                )

                # Collect unmapped BSNI entries
                for row in unmapped_bsni_df.iter_rows(named=True):
                    unmapped_bsni.append(
                        {
                            "singkatan": row.get("singkatan_nama_kota", ""),
                            "nama_kota": row.get("nama_kota", ""),
                            "kabupaten_kota": row.get("kabupaten_kota", ""),
                            "provinsi": row.get("provinsi", ""),
                        }
                    )

        return df_district, unmatched_names, unmapped_bsni

    @error_handler(operation_name="kabupaten_kota_detail_extraction", log_errors=True)
    def kabupaten_kota_detail(
        self, start_page: int, end_page: int, show_progress: bool = True
    ) -> pl.DataFrame:
        """
        Extract subdistrict/village table.

        Args:
            start_page: Starting page number (1-based)
            end_page: Ending page number (1-based, inclusive)
            show_progress: Whether to display progress bar during extraction

        Returns:
            Polars DataFrame with subdistrict/village data
        """
        # Use specific settings for district tables
        subdistrict_village_settings = {}  # empty config
        table_rows = self._extract_with_settings(
            start_page,
            end_page,
            subdistrict_village_settings,
            table_format="kabupaten_kota_detail",
            show_progress=show_progress,
        )

        subdistrict_village_data = []

        # Context variables for hierarchical data
        current_province = {
            "kode_provinsi": "",
            "provinsi": "",
            "jumlah_kabupaten": 0,
            "jumlah_kota": 0,
        }

        current_regency = {
            "kabupaten_kota": "",
            "jumlah_kecamatan": 0,
            "jumlah_kelurahan": 0,
            "jumlah_desa": 0,
        }

        current_district = {"kecamatan": "", "kelurahan": "", "desa": ""}

        district_counter = 0
        kelurahan_counter = 0

        # Helper for safe row access (avoid shadowing)
        def safe_row_val(row_data: List[Any], idx: int, default: Any = "") -> Any:
            return (
                row_data[idx]
                if len(row_data) > idx and row_data[idx] is not None
                else default
            )

        for row in table_rows:
            if not row or len(row) < 9:
                continue

            kode = safe_row_val(row, 0, "")
            provinsi_kabupaten = safe_row_val(row, 1, "")
            jumlah_kab = safe_row_val(row, 2, "")
            jumlah_kota = safe_row_val(row, 3, "")
            keterangan = safe_row_val(row, 8, "")

            if (
                kode == ""
                and provinsi_kabupaten
                and not provinsi_kabupaten.isdigit()
                and provinsi_kabupaten not in ["KAB", "KOTA", "KEC"]
            ):
                # Only process real historical districts with meaningful names
                data = DetailsData(
                    kode_provinsi=current_province["kode_provinsi"],
                    provinsi=current_province["provinsi"],
                    jumlah_kabupaten=0,
                    jumlah_kota=0,
                    kode_kabupaten_kota="",
                    kabupaten_kota="",
                    kode_kecamatan="",
                    kecamatan="",
                    kode_kelurahan="",
                    kelurahan="",
                    desa="",
                    luas_wilayah_km2=0.0,
                    keterangan=keterangan,
                )

                subdistrict_village_data.append(data)
                continue

            # Skip headers
            if (
                kode in ["K O D E", None]
                or provinsi_kabupaten in ["NAMA PROVINSI /\nKABUPATEN / KOTA", None]
                or jumlah_kab == "KAB"
            ):
                continue

            # Parse codes
            kode_parts = kode.split(".") if kode else []
            if len(kode_parts) < 1:
                continue

            kode_provinsi = kode_parts[0]
            kode_kabupaten_kota = (
                f"{kode_parts[0]}.{kode_parts[1]}" if len(kode_parts) > 1 else ""
            )
            kode_kecamatan = (
                f"{kode_parts[0]}.{kode_parts[1]}.{kode_parts[2]}"
                if len(kode_parts) > 2
                else ""
            )
            kode_kelurahan = kode if len(kode_parts) == 4 else ""

            if len(kode_parts) == 1:  # Province
                # Update context FIRST
                current_province.update(
                    {
                        "kode_provinsi": kode_provinsi,
                        "provinsi": provinsi_kabupaten,
                        "jumlah_kabupaten": int(jumlah_kab)
                        if jumlah_kab.isdigit()
                        else 0,
                        "jumlah_kota": int(jumlah_kota) if jumlah_kota.isdigit() else 0,
                    }
                )

                data = DetailsData(
                    kode_provinsi=kode_provinsi,
                    provinsi=provinsi_kabupaten,
                    jumlah_kabupaten=safe_row_val(row, 2, ""),
                    jumlah_kota=safe_row_val(row, 3, ""),
                    kode_kabupaten_kota="",
                    kabupaten_kota="",
                    kode_kecamatan="",
                    kecamatan="",
                    kode_kelurahan="",
                    kelurahan="",
                    desa="",
                    luas_wilayah_km2=safe_row_val(row, 7, ""),
                    keterangan=keterangan,
                )
                subdistrict_village_data.append(data)

            elif len(kode_parts) == 2:  # Regency
                district_counter = 0
                current_regency.update({"kabupaten_kota": provinsi_kabupaten})

                base_data = {
                    "kode_provinsi": kode_provinsi,
                    "provinsi": current_province["provinsi"],
                    "luas_wilayah_km2": safe_row_val(row, 7, ""),
                    "keterangan": keterangan,
                }

                data = DetailsData(
                    **base_data,
                    jumlah_kabupaten=0,
                    jumlah_kota=0,
                    kode_kabupaten_kota=kode_kabupaten_kota,
                    kabupaten_kota=provinsi_kabupaten,
                    kode_kecamatan="",
                    kecamatan="",
                    kode_kelurahan="",
                    kelurahan="",
                    desa="",
                )
                subdistrict_village_data.append(data)

            elif len(kode_parts) == 3:  # District
                district_counter += 1
                kelurahan_counter = 0
                kecamatan = safe_row_val(row, 4, "")
                if kecamatan.startswith(str(district_counter)):
                    kecamatan = (
                        str(district_counter)
                        + " "
                        + kecamatan[len(str(district_counter)) :].strip()
                    )
                current_district.update(
                    {
                        "kecamatan": kecamatan,
                        "kelurahan": safe_row_val(row, 5, ""),
                        "desa": safe_row_val(row, 6, ""),
                    }
                )

                base_data = {
                    "kode_provinsi": kode_provinsi,
                    "provinsi": current_province["provinsi"],
                    "luas_wilayah_km2": 0.0,  # Not in district data
                    "keterangan": keterangan,
                }

                data = DetailsData(
                    **base_data,
                    jumlah_kabupaten=0,
                    jumlah_kota=0,
                    kode_kabupaten_kota=kode_kabupaten_kota,
                    kabupaten_kota=current_regency["kabupaten_kota"],
                    kode_kecamatan=kode_kecamatan,
                    kecamatan=kecamatan,
                    kode_kelurahan="",
                    kelurahan="",
                    desa="",
                )

                subdistrict_village_data.append(data)

            elif len(kode_parts) == 4:  # Sub-district or Village
                kelurahan_counter += 1
                subdistrict_name = safe_row_val(row, 5, "")
                if subdistrict_name.startswith(str(kelurahan_counter)):
                    subdistrict_name = (
                        str(kelurahan_counter)
                        + " "
                        + subdistrict_name[len(str(kelurahan_counter)) :].strip()
                    )
                village_name = safe_row_val(row, 6, "")

                data = DetailsData(
                    kode_provinsi=kode_provinsi,
                    provinsi=current_province["provinsi"],
                    jumlah_kabupaten=0,
                    jumlah_kota=0,
                    kode_kabupaten_kota=kode_kabupaten_kota,
                    kabupaten_kota=current_regency["kabupaten_kota"],
                    kode_kecamatan=kode_kecamatan,
                    kecamatan=current_district["kecamatan"],
                    kode_kelurahan=kode_kelurahan,
                    kelurahan=subdistrict_name,
                    desa=village_name,
                    luas_wilayah_km2=0.0,  # Not in village data
                    keterangan=keterangan,
                )

                subdistrict_village_data.append(data)

        return pl.DataFrame([data.model_dump() for data in subdistrict_village_data])

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
            show_progress: Whether to display progress bar during extraction

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
    main_pdf_path = os.path.join(input_dir, file_name)

    # Use PDFTableExtractor
    table_extractor = PDFTableExtractor(main_pdf_path, start_page=1, end_page=5)

    # Extract province index data
    provinsi_index = table_extractor.provinsi_index(start_page=16, end_page=17)
    print(f"Extracted {len(provinsi_index)} rows for provinsi_index")

    # Extract province data
    provinsi = table_extractor.kabupaten_kota_index(start_page=1, end_page=5)
    print(f"Extracted {len(provinsi)} rows for provinsi")
