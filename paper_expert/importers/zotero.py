"""Zotero library importer.

Reads Zotero's local SQLite database (zotero.sqlite) and storage directory
to extract paper metadata, tags, and associated PDFs.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Any

from paper_expert.models.paper import PaperMetadata, PaperSource

logger = logging.getLogger(__name__)


def read_zotero_library(zotero_dir: Path) -> list[dict[str, Any]]:
    """Read papers from a Zotero data directory.

    Args:
        zotero_dir: Path to Zotero data directory (contains zotero.sqlite and storage/).

    Returns:
        List of dicts with keys: title, authors, year, doi, abstract, tags, pdf_path.
    """
    db_path = zotero_dir / "zotero.sqlite"
    if not db_path.exists():
        raise FileNotFoundError(f"Zotero database not found: {db_path}")

    storage_dir = zotero_dir / "storage"

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    try:
        items = _fetch_items(conn)
        results: list[dict[str, Any]] = []

        for item in items:
            item_id = item["itemID"]
            item_data = _fetch_item_data(conn, item_id)
            if not item_data.get("title"):
                continue

            tags = _fetch_item_tags(conn, item_id)
            pdf_path = _find_pdf(conn, item_id, storage_dir)

            results.append({
                "title": item_data.get("title", ""),
                "authors": item_data.get("authors", []),
                "year": item_data.get("year"),
                "doi": item_data.get("doi"),
                "abstract": item_data.get("abstract"),
                "venue": item_data.get("venue"),
                "tags": tags,
                "pdf_path": pdf_path,
            })

        return results
    finally:
        conn.close()


def _fetch_items(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Fetch all non-deleted, non-attachment items."""
    rows = conn.execute(
        """SELECT i.itemID, it.typeName
           FROM items i
           JOIN itemTypes it ON i.itemTypeID = it.itemTypeID
           WHERE i.itemID NOT IN (SELECT itemID FROM deletedItems)
           AND it.typeName NOT IN ('attachment', 'note')"""
    ).fetchall()
    return [dict(r) for r in rows]


def _fetch_item_data(conn: sqlite3.Connection, item_id: int) -> dict[str, Any]:
    """Fetch metadata fields for a Zotero item."""
    rows = conn.execute(
        """SELECT f.fieldName, iv.value
           FROM itemData id
           JOIN fields f ON id.fieldID = f.fieldID
           JOIN itemDataValues iv ON id.valueID = iv.valueID
           WHERE id.itemID = ?""",
        (item_id,),
    ).fetchall()

    data: dict[str, Any] = {}
    for row in rows:
        name = row["fieldName"]
        value = row["value"]
        if name == "title":
            data["title"] = value
        elif name == "DOI":
            data["doi"] = value
        elif name == "date":
            # Extract year from date
            if value and len(value) >= 4:
                try:
                    data["year"] = int(value[:4])
                except ValueError:
                    pass
        elif name == "abstractNote":
            data["abstract"] = value
        elif name in ("publicationTitle", "journalAbbreviation", "conferenceName"):
            data["venue"] = value

    # Fetch authors
    author_rows = conn.execute(
        """SELECT c.firstName, c.lastName
           FROM itemCreators ic
           JOIN creators c ON ic.creatorID = c.creatorID
           WHERE ic.itemID = ?
           ORDER BY ic.orderIndex""",
        (item_id,),
    ).fetchall()
    data["authors"] = [
        f"{r['firstName'] or ''} {r['lastName'] or ''}".strip()
        for r in author_rows
    ]

    return data


def _fetch_item_tags(conn: sqlite3.Connection, item_id: int) -> list[str]:
    """Fetch tags for a Zotero item."""
    rows = conn.execute(
        """SELECT t.name
           FROM itemTags it
           JOIN tags t ON it.tagID = t.tagID
           WHERE it.itemID = ?""",
        (item_id,),
    ).fetchall()
    return [r["name"] for r in rows]


def _find_pdf(
    conn: sqlite3.Connection, item_id: int, storage_dir: Path
) -> Path | None:
    """Find the PDF attachment for a Zotero item."""
    rows = conn.execute(
        """SELECT ia.itemID, ia.path
           FROM itemAttachments ia
           JOIN items i ON ia.itemID = i.itemID
           WHERE ia.parentItemID = ?
           AND ia.contentType = 'application/pdf'""",
        (item_id,),
    ).fetchall()

    for row in rows:
        att_path = row["path"]
        if att_path and att_path.startswith("storage:"):
            filename = att_path[len("storage:"):]
            # Zotero stores files in storage/<key>/filename
            att_key_row = conn.execute(
                "SELECT key FROM items WHERE itemID = ?", (row["itemID"],)
            ).fetchone()
            if att_key_row:
                pdf_path = storage_dir / att_key_row["key"] / filename
                if pdf_path.exists():
                    return pdf_path

    return None


def to_metadata_list(
    zotero_items: list[dict[str, Any]],
) -> list[tuple[PaperMetadata, Path | None]]:
    """Convert Zotero items to PaperMetadata + optional PDF path pairs."""
    results: list[tuple[PaperMetadata, Path | None]] = []
    for item in zotero_items:
        metadata = PaperMetadata(
            title=item["title"],
            authors=item.get("authors", []),
            year=item.get("year"),
            venue=item.get("venue"),
            doi=item.get("doi"),
            abstract=item.get("abstract"),
            source=PaperSource.ZOTERO,
        )
        pdf_path = item.get("pdf_path")
        results.append((metadata, Path(pdf_path) if pdf_path else None))
    return results
