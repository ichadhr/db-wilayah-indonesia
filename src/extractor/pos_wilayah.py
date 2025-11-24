#!/usr/bin/env python3
"""
Pos Wilayah Extractor - Postal Code Data Processor

This module processes postal code data by reading kabupaten/kota data,
scraping postal codes, and saving results with progress tracking.
Supports concurrent downloads for improved performance.
"""

import os
import time
import glob
import re
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List

import polars as pl

# Import scraper function
from extractor.scrapers.kodepos import scrape_kodepos

# Import models
from models.pos_wilayah import PosWilayah

# Import utilities
from utils.progress import progress_manager
from utils.errors import error_handler


class PosWilayahExtractor:
    """
    Extractor for postal code data from Indonesian regions.

    Handles reading kabupaten/kota data, scraping postal codes,
    saving results, and progress tracking.
    """

    def __init__(self, parquet_dir: str = "output", max_workers: int = 7):
        """
        Initialize the extractor.

        Args:
            parquet_dir: Directory containing kabupaten/kota parquet files
            max_workers: Maximum number of concurrent workers per province (default: 7)
        """
        self.parquet_dir = parquet_dir
        self.max_workers = max_workers
        # Log file should be in src/log directory, relative to this file
        self.log_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "log", "kodepos.log")
        
        # Regenerate log file for each run
        if os.path.exists(self.log_file):
            try:
                os.remove(self.log_file)
            except OSError:
                pass  # Ignore if file is in use or cannot be deleted

    def extract_pos_wilayah(self, logger=None, province_filter=None) -> dict:
        """
        Execute the complete postal code extraction pipeline.

        Args:
            logger: Optional logger instance for logging progress
            province_filter: Optional province name to filter processing

        Returns:
            Dict with processing statistics
        """
        if logger is None:
            logger = logging.getLogger(__name__)

        # Read kabupaten/kota list grouped by province
        kabupaten_kota_dict = self._read_kabupaten_kota_list(logger)

        # Filter provinces if specified
        if province_filter:
            kabupaten_kota_dict = {k: v for k, v in kabupaten_kota_dict.items() if k == province_filter}
            if not kabupaten_kota_dict:
                logger.warning(f"Province {province_filter} not found in data")
                return {"total_processed": 0, "with_results": 0, "no_results": 0}

        total_kabupaten_kota = sum(len(lst) for lst in kabupaten_kota_dict.values())
        logger.info(f"Found {total_kabupaten_kota} entries to process across {len(kabupaten_kota_dict)} provinces")

        # Track results
        processed = 0
        no_results = []
        province_results = {}

        with progress_manager.download_progress(
            total_items=total_kabupaten_kota,
            description="Scraping postal codes"
        ) as progress_ctx:

            for province, kabupaten_kota_list in kabupaten_kota_dict.items():
                province_results[province] = []
                
                # Process all kabupaten/kota in province concurrently
                with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                    # Submit all tasks
                    future_to_kabkota = {
                        executor.submit(self._scrape_single, province, kabupaten_kota): kabupaten_kota
                        for kabupaten_kota in kabupaten_kota_list
                    }
                    
                    # Collect results as they complete
                    for future in as_completed(future_to_kabkota):
                        kabupaten_kota = future_to_kabkota[future]
                        try:
                            results = future.result()
                            if results:
                                province_results[province].extend(results)
                            else:
                                no_results.append(kabupaten_kota)
                        except Exception as e:
                            logger.error(f"Error processing {kabupaten_kota}: {e}")
                            no_results.append(kabupaten_kota)
                        
                        processed += 1
                        progress_ctx.advance(1)
                        progress_ctx.update(description=f"Scraping postal codes {kabupaten_kota}")

                # Save accumulated results for the province
                if province_results[province]:
                    self._save_province_results(province, province_results[province], logger)
                
                # Rate limiting - sleep between provinces
                time.sleep(1)

        # Summary
        stats = {
            "total_processed": processed,
            "with_results": processed - len(no_results),
            "no_results": len(no_results)
        }

        logger.info("Scraping completed!")
        logger.info(f"Total processed: {stats['total_processed']}")
        logger.info(f"With results: {stats['with_results']}")
        logger.info(f"No results: {stats['no_results']}")

        if no_results:
            logger.info(f"Entries with no results saved to {self.log_file}: {len(no_results)}")

        return stats

    def _read_kabupaten_kota_list(self, logger) -> dict[str, List[str]]:
        """
        Read kabupaten/kota list from parquet files grouped by province.

        Args:
            logger: Logger instance

        Returns:
            Dict mapping province names to lists of kabupaten/kota names
        """
        files = glob.glob(os.path.join(self.parquet_dir, 'parquet', '*', '*_kabupaten_kota_index.parquet'))
        province_dict = {}
        for file in files:
            province = os.path.basename(os.path.dirname(file))
            df = pl.read_parquet(file)
            kabupaten_kota_list = df['kabupaten_kota'].unique().to_list()
            province_dict[province] = kabupaten_kota_list
        return province_dict

    def _scrape_single(self, province: str, kabupaten_kota: str) -> List[PosWilayah]:
        """
        Scrape postal codes for a single kabupaten/kota.

        Args:
            province: Province name for logging
            kabupaten_kota: Name of the kabupaten/kota

        Returns:
            List of PosWilayah objects
        """
        # Clean the name
        clean_name = kabupaten_kota.replace('"', '').strip()

        # Define regex replacements for fixing search terms
        replacements = [
            (r'Mukomuko', 'Muko Muko'),
            (r'Pohuwato', 'Pahuwato'),
            (r'Parepare', 'Pare Pare'),
            (r'Toli-Toli', 'Toli Toli'),
            (r'Tanjungbalai', 'Tanjung Balai'),
            (r'Kabupaten Pangkajene dan Kepulauan', 'Kab. Pangkajene Kepulauan'), # Specific case (full text)
            (r'Kabupaten Administrasi Kepulauan Seribu', 'Kab. Adm. Kep. Seribu'),  # Specific case (full text)
            (r'Kabupaten Kepulauan Siau Tagulandang Biaro', 'Kab. Kep. Siau Tagulandang Biaro'),  # Specific case (full text)
            (r'Kabupaten Timor Tengah Selatan', 'Kab Timor Tengah Selatan'), # Specific case (full text)
            (r'Kabupaten', 'Kab.'),  # Shorten Kabupaten to Kab. (case insensitive)
            (r'Administrasi', 'Adm.'),  # Shorten Administrasi to Adm. (case insensitive)
        ]

        # Apply all replacements in sequence
        search_term = clean_name
        for pattern, replacement in replacements:
            search_term = re.sub(pattern, replacement, search_term, flags=re.IGNORECASE)

        try:
            results = scrape_kodepos(search_term)

            if not results:
                self._log_error(province, kabupaten_kota, search_term, "records not found")
                return []

            # 4. VALIDATION: Filter results to ensure they belong to the correct region
            filtered_results = []

            # Normalize targets for comparison
            target_prov = province.replace('_', ' ').lower()

            # Use search_term for validation to match normalized names
            target_kab = search_term.lower()

            # Create space-insensitive targets for robust matching
            target_prov_clean = target_prov.replace(" ", "").replace("-", "")
            target_kab_clean = target_kab.replace(" ", "").replace("-", "").replace(".", "")

            for res in results:
                # Normalize the raw data for matching
                res_prov = res['provinsi'].lower()
                res_kab = res['kabupaten_kota'].lower()

                res_prov_clean = res_prov.replace(" ", "").replace("-", "")
                res_kab_clean = res_kab.replace(" ", "").replace("-", "").replace(".", "")

                # Check if result matches expected province and kabupaten/kota
                # We use containment to handle minor differences (e.g. "dki jakarta" vs "jakarta")

                # Province check
                prov_match = target_prov_clean in res_prov_clean or res_prov_clean in target_prov_clean

                # Kabupaten check
                kab_match = target_kab_clean in res_kab_clean or res_kab_clean in target_kab_clean

                if prov_match and kab_match:
                    filtered_results.append(res)

            if not filtered_results:
                # Debug: log first few results for diagnosis
                debug_count = min(5, len(results))
                for i in range(debug_count):
                    res = results[i]
                    self._log_error(province, kabupaten_kota, search_term, f"Sample result {i+1}: kodepos='{res['kodepos']}', kec='{res['kecamatan']}', kel='{res['desa_kelurahan']}', kab='{res['kabupaten_kota']}', prov='{res['provinsi']}' | targets: prov='{target_prov_clean}', kab='{target_kab_clean}'")
                self._log_error(province, kabupaten_kota, search_term, f"Found {len(results)} results but none matched region")
                return []

            # Instantiate PosWilayah objects only for filtered results
            pos_wilayah_results = [PosWilayah(**res) for res in filtered_results]

            return pos_wilayah_results
            
        except Exception as e:
            self._log_error(province, kabupaten_kota, search_term, str(e))
            return []

    def _log_error(self, province: str, original: str, search_term: str, reason: str) -> None:
        """
        Log error to kodepos.log file with province context.

        Args:
            province: Province name
            original: Original name of the kabupaten/kota
            search_term: Search term used after replacements
            reason: Error reason or message
        """
        os.makedirs(os.path.dirname(self.log_file), exist_ok=True)

        with open(self.log_file, 'a', encoding='utf-8') as f:
            timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
            f.write(f"{timestamp} - {province} - {original} -> {search_term} - {reason}\n")

    def _save_province_results(self, province: str, results: List[PosWilayah], logger) -> None:
        """
        Save accumulated scraping results for a province to a single Parquet file.

        Args:
            province: Province name
            results: List of PosWilayah objects for the province
            logger: Logger instance
        """
        logger.info(f"Attempting to save {len(results)} results for province {province}")
        if not results:
            logger.warning(f"No results to save for province {province}")
            return

        filename = f"{province}_kabupaten_kota_pos.parquet"
        # Use parquet_dir as base, don't hardcode 'src'
        dir_path = os.path.join(self.parquet_dir, "parquet", province)
        os.makedirs(dir_path, exist_ok=True)
        file_path = os.path.join(dir_path, filename)

        try:
            # Convert PosWilayah objects to dictionaries for DataFrame
            results_dicts = [result.model_dump() for result in results]
            df = pl.DataFrame(results_dicts)
            df.write_parquet(file_path)
            logger.info(f"Successfully saved {len(results)} entries to: {file_path}")
            print(f"\nSaved {len(results)} entries to: {file_path}")
        except Exception as e:
            logger.error(f"Failed to save parquet file {file_path}: {e}")
            raise


# For backward compatibility, if run as script
if __name__ == "__main__":
    import sys
    province_filter = sys.argv[1] if len(sys.argv) > 1 else None
    with error_handler("postal_code_processing"):
        extractor = PosWilayahExtractor(parquet_dir="output")
        stats = extractor.extract_pos_wilayah(province_filter=province_filter)
        print(f"Processing completed: {stats}")