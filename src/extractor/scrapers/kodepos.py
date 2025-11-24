#!/usr/bin/env python3
"""
Kodepos Scraper - Postal Code Data Extractor

This module provides scraping functionality for postal code data from kodepos.posindonesia.co.id
for Indonesian regions (kabupaten/kota).
"""

import requests
from bs4 import BeautifulSoup
from typing import List
import re
from urllib.parse import quote

# Import our utilities
from utils.errors import NetworkError
from utils.text_utils import format_string


def scrape_kodepos(search_term: str) -> List[dict]:
    """
    Scrape postal code data for a given search term.

    Args:
        search_term: The kabupaten/kota name to search for

    Returns:
        List of dictionaries with scraped data
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
                    'kabupaten_kota': to_title_case(format_string(cells[4].text)),
                    'provinsi': to_title_case(format_string(cells[5].text)).replace('Dki', 'daerah khusus ibukota', 1),
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

