"""arXiv API adapter.

Domain-specific source for CS/AI and physics papers. Provides free PDF access.

API docs: https://info.arxiv.org/help/api/
"""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET

import httpx

from paper_expert.models.paper import PaperMetadata, PaperSource, SearchResult

logger = logging.getLogger(__name__)

ARXIV_API_BASE = "https://export.arxiv.org/api/query"
ARXIV_PDF_BASE = "https://arxiv.org/pdf/"
ATOM_NS = "{http://www.w3.org/2005/Atom}"
ARXIV_NS = "{http://arxiv.org/schemas/atom}"


class ArxivAdapter:
    """Adapter for the arXiv API."""

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(timeout=30.0)

    async def close(self) -> None:
        await self._client.aclose()

    async def search(
        self, query: str, limit: int = 20, sort_by: str = "relevance"
    ) -> list[SearchResult]:
        """Search arXiv for papers.

        Args:
            query: Search query (supports arXiv query syntax).
            limit: Max results.
            sort_by: "relevance" or "lastUpdatedDate" or "submittedDate".
        """
        params = {
            "search_query": f"all:{query}",
            "start": 0,
            "max_results": min(limit, 100),
            "sortBy": sort_by,
            "sortOrder": "descending",
        }

        resp = await self._client.get(ARXIV_API_BASE, params=params)
        resp.raise_for_status()

        return self._parse_feed(resp.text)

    async def get_by_id(self, arxiv_id: str) -> PaperMetadata | None:
        """Fetch a paper by arXiv ID (e.g., '2401.12345' or '2401.12345v2')."""
        clean_id = arxiv_id.replace("arxiv:", "").replace("arXiv:", "")
        params = {"id_list": clean_id}
        resp = await self._client.get(ARXIV_API_BASE, params=params)
        resp.raise_for_status()

        results = self._parse_feed(resp.text)
        if not results:
            return None

        r = results[0]
        return PaperMetadata(
            title=r.title,
            authors=r.authors,
            year=r.year,
            abstract=r.abstract,
            arxiv_id=r.arxiv_id,
            doi=r.doi,
            open_access_pdf_url=r.open_access_pdf_url,
            source=PaperSource.ARXIV,
        )

    @staticmethod
    def pdf_url(arxiv_id: str) -> str:
        """Construct PDF download URL for an arXiv ID."""
        clean_id = arxiv_id.replace("arxiv:", "").replace("arXiv:", "")
        return f"{ARXIV_PDF_BASE}{clean_id}.pdf"

    # ── XML parsing ──────────────────────────────────────────

    def _parse_feed(self, xml_text: str) -> list[SearchResult]:
        root = ET.fromstring(xml_text)
        results: list[SearchResult] = []

        for entry in root.findall(f"{ATOM_NS}entry"):
            results.append(self._parse_entry(entry))

        return results

    def _parse_entry(self, entry: ET.Element) -> SearchResult:
        title = (entry.findtext(f"{ATOM_NS}title") or "").strip().replace("\n", " ")
        summary = (entry.findtext(f"{ATOM_NS}summary") or "").strip().replace("\n", " ")

        authors: list[str] = []
        for author_el in entry.findall(f"{ATOM_NS}author"):
            name = author_el.findtext(f"{ATOM_NS}name")
            if name:
                authors.append(name.strip())

        # Extract arXiv ID from the entry ID URL
        entry_id = entry.findtext(f"{ATOM_NS}id") or ""
        arxiv_id = self._extract_arxiv_id(entry_id)

        # Extract year from published date
        published = entry.findtext(f"{ATOM_NS}published") or ""
        year = int(published[:4]) if len(published) >= 4 else None

        # Look for DOI in links
        doi: str | None = None
        for link in entry.findall(f"{ATOM_NS}link"):
            href = link.get("href", "")
            if "doi.org" in href:
                doi = href.split("doi.org/")[-1]

        pdf_url = f"{ARXIV_PDF_BASE}{arxiv_id}.pdf" if arxiv_id else None

        return SearchResult(
            title=title,
            authors=authors,
            year=year,
            doi=doi,
            arxiv_id=arxiv_id,
            abstract=summary,
            open_access_pdf_url=pdf_url,
            source=PaperSource.ARXIV,
        )

    @staticmethod
    def _extract_arxiv_id(entry_url: str) -> str | None:
        """Extract arXiv ID from entry URL like http://arxiv.org/abs/2401.12345v2."""
        match = re.search(r"arxiv\.org/abs/(.+?)(?:v\d+)?$", entry_url)
        if match:
            return match.group(1)
        return None
