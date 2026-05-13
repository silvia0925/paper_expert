"""BibTeX file importer.

Parses .bib files and converts entries to PaperMetadata for library import.
Compatible with bibtexparser v1.x (stable) and v2.x (beta).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import bibtexparser

from paper_expert.models.paper import PaperMetadata, PaperSource

logger = logging.getLogger(__name__)

# Detect bibtexparser version
_HAS_V2 = hasattr(bibtexparser, "parse")


def parse_bibtex(bib_path: Path) -> list[PaperMetadata]:
    """Parse a BibTeX file and return a list of PaperMetadata.

    Args:
        bib_path: Path to the .bib file.

    Returns:
        List of PaperMetadata objects extracted from the BibTeX entries.
    """
    if not bib_path.exists():
        raise FileNotFoundError(f"BibTeX file not found: {bib_path}")

    bib_text = bib_path.read_text(encoding="utf-8")

    if _HAS_V2:
        library = bibtexparser.parse(bib_text)
        entries = library.entries
    else:
        parser = bibtexparser.bparser.BibTexParser(common_strings=True)
        library = bibtexparser.loads(bib_text, parser=parser)
        entries = library.entries

    results: list[PaperMetadata] = []
    for entry in entries:
        metadata = _entry_to_metadata(entry)
        if metadata:
            results.append(metadata)

    logger.info("Parsed %d entries from %s", len(results), bib_path)
    return results


def _entry_to_metadata(entry: Any) -> PaperMetadata | None:
    """Convert a single BibTeX entry to PaperMetadata."""
    # v1 entries are plain dicts, v2 has .fields_dict
    if hasattr(entry, "fields_dict"):
        fields = entry.fields_dict
    elif isinstance(entry, dict):
        fields = entry
    else:
        fields = {}

    title = _get_field(fields, "title")
    if not title:
        return None

    # Clean LaTeX formatting from title
    title = _clean_latex(title)

    # Extract authors
    author_str = _get_field(fields, "author")
    authors = _parse_authors(author_str) if author_str else []

    # Extract year
    year_str = _get_field(fields, "year")
    year = int(year_str) if year_str and year_str.isdigit() else None

    # Extract venue
    venue = (
        _get_field(fields, "journal")
        or _get_field(fields, "booktitle")
        or _get_field(fields, "publisher")
    )
    if venue:
        venue = _clean_latex(venue)

    doi = _get_field(fields, "doi")
    abstract = _get_field(fields, "abstract")
    if abstract:
        abstract = _clean_latex(abstract)

    # Check for arXiv ID in eprint field
    arxiv_id = _get_field(fields, "eprint")
    archive_prefix = _get_field(fields, "archiveprefix")
    if arxiv_id and archive_prefix and archive_prefix.lower() != "arxiv":
        arxiv_id = None

    return PaperMetadata(
        title=title,
        authors=authors,
        year=year,
        venue=venue,
        doi=doi,
        abstract=abstract,
        arxiv_id=arxiv_id,
        source=PaperSource.BIBTEX,
    )


def _get_field(fields: dict, key: str) -> str | None:
    """Get a field value from bibtexparser fields dict."""
    field = fields.get(key)
    if field is None:
        return None
    # bibtexparser v2 uses Field objects with .value
    if hasattr(field, "value"):
        return str(field.value).strip()
    return str(field).strip() if field else None


def _parse_authors(author_str: str) -> list[str]:
    """Parse BibTeX author string ('Last, First and Last, First')."""
    authors: list[str] = []
    for part in author_str.split(" and "):
        name = part.strip()
        if not name:
            continue
        name = _clean_latex(name)
        # Convert "Last, First" to "First Last"
        if ", " in name:
            parts = name.split(", ", 1)
            name = f"{parts[1]} {parts[0]}"
        authors.append(name)
    return authors


def _clean_latex(text: str) -> str:
    """Remove common LaTeX formatting from text."""
    text = text.replace("{", "").replace("}", "")
    text = text.replace("\\&", "&")
    text = text.replace("\\textit", "").replace("\\textbf", "")
    text = text.replace("\\emph", "")
    text = text.replace("~", " ")
    return text.strip()
