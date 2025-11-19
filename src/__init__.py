"""
Indonesian Regional Data Extraction Pipeline

Extracts and processes regional administrative data from PDF documents
based on SNI 7657:2010 standards.
"""

__version__ = "0.1.0"

from .config.settings import settings
from .pipeline.orchestrator import PipelineOrchestrator, PipelineConfig

__all__ = [
    'settings',
    'PipelineOrchestrator',
    'PipelineConfig',
]
