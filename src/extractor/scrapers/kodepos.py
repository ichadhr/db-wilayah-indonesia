#!/usr/bin/env python3
"""
Kodepos Scraper - Postal Code Data Extractor

This module scrapes postal code data from kodepos.posindonesia.co.id
for Indonesian regions (kabupaten/kota) with comprehensive error handling
and progress tracking capabilities.
"""

import os
import csv
import json
import time
import requests
from bs4 import BeautifulSoup
from typing import List, Dict
import re
from urllib.parse import quote

# Import our utilities
from utils.progress import progress_manager
from utils.errors import error_handler, NetworkError
from utils.converter import format_string


def scrape_kodepos(search_term: str) -> List[Dict[str, str]]:
    """
    Scrape postal code data for a given search term.

    Args:
        search_term: The kabupaten/kota name to search for

    Returns:
        List of postal code entries
    """
    url = 'https://kodepos.posindonesia.co.id/CariKodepos'
    data = f'kodepos={quote(search_term)}'

    try:
        response = requests.post(
            url,
            data=data,
            headers={
                'Content-Type': 'application/x-www-form-urlencoded',
            },
            timeout=30
        )

        if not response.ok:
            raise NetworkError(
                f"HTTP error! status: {response.status_code}",
                url=url,
                status_code=response.status_code
            )

        soup = BeautifulSoup(response.text, 'html.parser')
        table = soup.find('table', id='list-data')

        if not table:
            return []

        results = []
        rows = table.find_all('tr')  # type: ignore

        for row in rows:
            cells = row.find_all('td')  # type: ignore
            if len(cells) == 6:
                entry = {
                    'kodepos': format_string(cells[1].text),
                    'desa_kelurahan': format_string(cells[2].text),
                    'kecamatan': format_string(cells[3].text),
                    'kota_kabupaten': to_title_case(format_string(cells[4].text)),
                    'provinsi': to_title_case(format_string(cells[5].text)).replace('Dki', 'DKI', 1),
                }
                results.append(entry)

        return results

    except requests.RequestException as e:
        raise NetworkError(f"Network error while scraping {search_term}: {str(e)}", url=url)


def to_kebab_case(text: str) -> str:
    """
    Convert text to kebab-case for filename generation.

    Args:
        text: Input text

    Returns:
        Kebab-case string
    """
    return re.sub(
        r'[^a-z0-9\s-]',
        '',
        text.lower()
    ).replace(' ', '-').replace('--', '-').strip('-')


def to_title_case(text: str) -> str:
    """
    Convert text to title case.

    Args:
        text: Input text

    Returns:
        Title case string
    """
    return re.sub(r'\b\w', lambda m: m.group(0).upper(), text.lower())


def main():
    """Main scraping function."""
    csv_path = '../csv/tbl_kabkot.csv'
    scrap_dir = '../scrap'

    # Create scrap directory if it doesn't exist
    os.makedirs(scrap_dir, exist_ok=True)

    # Read CSV data
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    print(f"Found {len(rows)} entries to process")

    # Track results
    processed = 0
    no_results = []

    with progress_manager.pdf_processing_progress(
        total_pages=len(rows),
        description="Scraping postal codes"
    ) as progress_ctx:

        for row in rows:
            kabupaten_kota = row['kabupaten_kota'].replace('"', '').strip()

            # Remove "Kota" or "Kabupaten" prefix for better search results
            search_term = re.sub(r'^(Kota|Kabupaten)\s+', '', kabupaten_kota)

            try:
                print(f"Processing: {kabupaten_kota}")

                results = scrape_kodepos(search_term)

                if not results:
                    # Log to no_results.csv
                    with open('../no_results.csv', 'a', encoding='utf-8') as f:
                        f.write(f"{kabupaten_kota}\n")
                    no_results.append(kabupaten_kota)
                    print(f"No results for: {kabupaten_kota}")
                else:
                    # Save to JSON file
                    filename = f"{to_kebab_case(kabupaten_kota)}.json"
                    file_path = os.path.join(scrap_dir, filename)

                    with open(file_path, 'w', encoding='utf-8') as f:
                        json.dump(results, f, ensure_ascii=False, indent=2)

                    print(f"Saved {len(results)} entries to: {file_path}")

                processed += 1
                progress_ctx.update_stats(
                    provinces_found=len(rows) - len(no_results),
                    kabupaten_kota_count=processed
                )
                progress_ctx.advance(1)

            except Exception as e:
                print(f"Error processing {kabupaten_kota}: {e}")
                progress_ctx.advance(1)
                continue

            # Rate limiting - wait 1 second between requests
            time.sleep(1)

    # Summary
    print("\nScraping completed!")
    print(f"Total processed: {processed}")
    print(f"With results: {processed - len(no_results)}")
    print(f"No results: {len(no_results)}")

    if no_results:
        print(f"\nEntries with no results saved to no_results.csv: {len(no_results)}")


if __name__ == "__main__":
    with error_handler("postal_code_scraping"):
        main()