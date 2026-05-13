"""Pydantic data models for Paper Expert."""

from __future__ import annotations

import json
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class PaperState(str, Enum):
    """Paper state in the knowledge base."""

    FULL_TEXT = "full-text"
    METADATA_ONLY = "metadata-only"
    PENDING = "pending"


class PaperSource(str, Enum):
    """Source where the paper was discovered."""

    SEMANTIC_SCHOLAR = "semantic_scholar"
    OPENALEX = "openalex"
    ARXIV = "arxiv"
    IEEE = "ieee"
    MANUAL = "manual"
    ZOTERO = "zotero"
    BIBTEX = "bibtex"


class TagLevel(str, Enum):
    """Tag classification level."""

    L0 = "L0"  # User-defined top-level domains
    L1 = "L1"  # LLM-generated sub-topics (controlled vocabulary)
    L2 = "L2"  # Free-form user tags


class Tag(BaseModel):
    """A tag attached to a paper."""

    level: TagLevel
    tag: str
    confidence: float | None = None
    suggested: bool = False


class PaperMetadata(BaseModel):
    """Metadata for a paper, typically from an external API."""

    title: str
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    venue: str | None = None
    abstract: str | None = None
    doi: str | None = None
    arxiv_id: str | None = None
    s2_paper_id: str | None = None
    citation_count: int = 0
    open_access_pdf_url: str | None = None
    references: list[str] = Field(default_factory=list)  # DOIs or S2 IDs
    source: PaperSource = PaperSource.MANUAL


class Paper(BaseModel):
    """A paper in the knowledge base."""

    id: int
    doi: str | None = None
    title: str
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    venue: str | None = None
    abstract: str | None = None
    source: PaperSource = PaperSource.MANUAL
    state: PaperState = PaperState.PENDING
    arxiv_id: str | None = None
    s2_paper_id: str | None = None
    citation_count: int = 0
    pdf_path: str | None = None
    parsed_path: str | None = None
    date_added: datetime | None = None
    tags: list[Tag] = Field(default_factory=list)

    @field_validator("authors", mode="before")
    @classmethod
    def parse_authors(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            return json.loads(v)
        return v

    @classmethod
    def from_db_row(cls, row: dict[str, Any], tags: list[dict[str, Any]] | None = None) -> Paper:
        """Create a Paper from a database row dict."""
        authors = row.get("authors_json", "[]")
        if isinstance(authors, str):
            authors = json.loads(authors)

        paper_tags: list[Tag] = []
        if tags:
            paper_tags = [
                Tag(
                    level=TagLevel(t["level"]),
                    tag=t["tag"],
                    confidence=t.get("confidence"),
                    suggested=bool(t.get("suggested", 0)),
                )
                for t in tags
            ]

        return cls(
            id=row["id"],
            doi=row.get("doi"),
            title=row["title"],
            authors=authors,
            year=row.get("year"),
            venue=row.get("venue"),
            abstract=row.get("abstract"),
            source=PaperSource(row.get("source", "manual")),
            state=PaperState(row.get("state", "pending")),
            arxiv_id=row.get("arxiv_id"),
            s2_paper_id=row.get("s2_paper_id"),
            citation_count=row.get("citation_count", 0),
            pdf_path=row.get("pdf_path"),
            parsed_path=row.get("parsed_path"),
            date_added=row.get("date_added"),
            tags=paper_tags,
        )


class SearchResult(BaseModel):
    """A single result from a paper search."""

    title: str
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    venue: str | None = None
    doi: str | None = None
    arxiv_id: str | None = None
    s2_paper_id: str | None = None
    citation_count: int = 0
    abstract: str | None = None
    open_access_pdf_url: str | None = None
    source: PaperSource = PaperSource.SEMANTIC_SCHOLAR
    in_library: bool = False


class CitationEdge(BaseModel):
    """A citation relationship between two papers."""

    citing_paper_id: int
    cited_paper_id: int


class ClassificationResult(BaseModel):
    """Result of LLM-based paper classification."""

    l0_tags: list[str] = Field(default_factory=list)
    l1_tags: list[Tag] = Field(default_factory=list)
    raw_l1_output: str | None = None
