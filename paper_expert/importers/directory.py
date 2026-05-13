"""Local directory importer.

Recursively scans a directory for PDF files, parses each to extract
metadata, and resolves identity via Semantic PaperExpert.
"""

from __future__ import annotations

import logging
from pathlib import Path

from paper_expert.models.paper import PaperMetadata, PaperSource

logger = logging.getLogger(__name__)


def scan_pdfs(directory: Path, recursive: bool = True) -> list[Path]:
    """Scan a directory for PDF files.

    Args:
        directory: Directory to scan.
        recursive: Whether to scan subdirectories.

    Returns:
        List of PDF file paths found.
    """
    if not directory.exists():
        raise FileNotFoundError(f"Directory not found: {directory}")

    if recursive:
        pdfs = sorted(directory.rglob("*.pdf"))
    else:
        pdfs = sorted(directory.glob("*.pdf"))

    logger.info("Found %d PDF files in %s", len(pdfs), directory)
    return pdfs


def pdf_to_metadata(pdf_path: Path) -> PaperMetadata:
    """Create a minimal PaperMetadata from a PDF file path.

    The title is derived from the filename. Full metadata should be
    resolved later via Semantic PaperExpert title search.
    """
    title = pdf_path.stem.replace("_", " ").replace("-", " ").strip()

    return PaperMetadata(
        title=title,
        source=PaperSource.MANUAL,
    )
