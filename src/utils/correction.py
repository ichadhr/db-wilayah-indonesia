import os
import csv
import logging
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class CorrectionLoader:
    """
    Loads and applies corrections from correction.csv.
    """
    
    _instance = None
    _corrections: Dict[str, Dict[str, str]] = {} # fix_source -> {source_value -> corrected_value}
    _metadata: Dict[str, Dict[str, dict]] = {} # fix_source -> {source_value -> full_row_dict}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(CorrectionLoader, cls).__new__(cls)
            cls._instance._load_corrections()
        return cls._instance

    def _load_corrections(self):
        """Load corrections from CSV file."""
        csv_path = os.path.join(os.path.dirname(__file__), "correction.csv")
        
        if not os.path.exists(csv_path):
            logger.warning(f"Correction file not found: {csv_path}")
            return

        try:
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                
                # Validate CSV headers
                expected_headers = {'fix_source', 'source_value', 'corrected_value'}
                if not expected_headers.issubset(set(reader.fieldnames or [])):
                    logger.error(f"Invalid CSV format. Expected headers: {expected_headers}, got: {reader.fieldnames}")
                    return
                
                count = 0
                for row in reader:
                    fix_source = row.get('fix_source', '').strip()
                    source_value = row.get('source_value', '').strip()
                    corrected_value = row.get('corrected_value', '').strip()
                    
                    if not fix_source or not source_value:
                        continue
                        
                    if fix_source not in self._corrections:
                        self._corrections[fix_source] = {}
                        self._metadata[fix_source] = {}
                        
                    self._corrections[fix_source][source_value] = corrected_value
                    self._metadata[fix_source][source_value] = row
                    count += 1
                
                logger.info(f"Loaded {count} corrections from {csv_path}")
        except Exception as e:
            logger.error(f"Failed to load corrections: {e}")

    def get_correction(self, value: str, fix_source: str) -> Optional[str]:
        """
        Get corrected value for a given source value and fix source.
        
        Args:
            value: The value to correct
            fix_source: The source of the fix (e.g., 'bsni', 'kecamatan_index')
            
        Returns:
            Corrected value if found, None otherwise
        """
        if fix_source in self._corrections:
            return self._corrections[fix_source].get(value)
        return None

    def get_metadata(self, value: str, fix_source: str) -> Optional[dict]:
        """
        Get full metadata for a correction.
        
        Args:
            value: The source value
            fix_source: The source of the fix
            
        Returns:
            Dictionary containing the full CSV row for the correction
        """
        if fix_source in self._metadata:
            return self._metadata[fix_source].get(value)
        return None
