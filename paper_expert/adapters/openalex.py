"""OpenAlex API adapter.

Supplementary search source with broad coverage (250M+ works).
Completely free, no authentication required.

API docs: https://docs.openalex.org/
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from paper_expert.models.paper import PaperMetadata, PaperSource, SearchResult

logger = logging.getLogger(__name__)

OPENALEX_API_BASE = "https://api.openalex.org"


class OpenAlexAdapter:
    """Adapter for the OpenAlex API."""

    def __init__(self, mailto: str = "") -> None:
        params: dict[str, str] = {}
        if mailto:
            params["mailto"] = mailto
        self._client = httpx.AsyncClient(
            base_url=OPENALEX_API_BASE,
            params=params,
            timeout=30.0,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def search(
        self,
        query: str,
        limit: int = 20,
        year: int | None = None,
        venue: str | None = None,
    ) -> list[SearchResult]:
        """Search for works by text query."""
        params: dict[str, Any] = {
            "search": query,
            "per_page": min(limit, 200),
            "sort": "relevance_score:desc",
        }

        filters: list[str] = []
        if year:
            filters.append(f"publication_year:{year}")
        if venue:
            filters.append(f"primary_location.source.display_name.search:{venue}")
        if filters:
            params["filter"] = ",".join(filters)

        resp = await self._client.get("/works", params=params)
        resp.raise_for_status()
        data = resp.json()

        results: list[SearchResult] = []
        for item in data.get("results", []):
            results.append(self._to_search_result(item))
        return results

    async def get_work(self, openalex_id: str) -> PaperMetadata | None:
        """Fetch a single work by OpenAlex ID or DOI."""
        try:
            resp = await self._client.get(f"/works/{openalex_id}")
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise

        return self._to_metadata(resp.json())

    async def get_work_by_doi(self, doi: str) -> PaperMetadata | None:
        """Fetch a work by DOI."""
        return await self.get_work(f"doi:{doi}")

    # ── Conversion helpers ──────────────────────────────────

    def _extract_authors(self, work: dict[str, Any]) -> list[str]:
        authorships = work.get("authorships", [])
        return [
            a.get("author", {}).get("display_name", "")
            for a in authorships
            if a.get("author", {}).get("display_name")
        ]

    def _extract_doi(self, work: dict[str, Any]) -> str | None:
        doi = work.get("doi")
        if doi and doi.startswith("https://doi.org/"):
            return doi[len("https://doi.org/"):]
        return doi

    def _extract_venue(self, work: dict[str, Any]) -> str | None:
        loc = work.get("primary_location") or {}
        source = loc.get("source") or {}
        return source.get("display_name")

    def _extract_oa_url(self, work: dict[str, Any]) -> str | None:
        oa = work.get("open_access") or {}
        return oa.get("oa_url")

    def _to_search_result(self, work: dict[str, Any]) -> SearchResult:
        return SearchResult(
            title=work.get("display_name", work.get("title", "")),
            authors=self._extract_authors(work),
            year=work.get("publication_year"),
            venue=self._extract_venue(work),
            doi=self._extract_doi(work),
            citation_count=work.get("cited_by_count", 0),
            abstract=self._reconstruct_abstract(work),
            open_access_pdf_url=self._extract_oa_url(work),
            source=PaperSource.OPENALEX,
        )

    def _to_metadata(self, work: dict[str, Any]) -> PaperMetadata:
        ref_ids: list[str] = []
        for ref_url in work.get("referenced_works", []):
            if isinstance(ref_url, str):
                ref_ids.append(ref_url.split("/")[-1])

        return PaperMetadata(
            title=work.get("display_name", work.get("title", "")),
            authors=self._extract_authors(work),
            year=work.get("publication_year"),
            venue=self._extract_venue(work),
            doi=self._extract_doi(work),
            citation_count=work.get("cited_by_count", 0),
            abstract=self._reconstruct_abstract(work),
            open_access_pdf_url=self._extract_oa_url(work),
            references=ref_ids,
            source=PaperSource.OPENALEX,
        )

    def _reconstruct_abstract(self, work: dict[str, Any]) -> str | None:
        """Reconstruct abstract from OpenAlex inverted index format."""
        inverted = work.get("abstract_inverted_index")
        if not inverted:
            return None

        word_positions: list[tuple[int, str]] = []
        for word, positions in inverted.items():
            for pos in positions:
                word_positions.append((pos, word))
        word_positions.sort()
        return " ".join(w for _, w in word_positions)
