"""Semantic PaperExpert API adapter.

Primary search source. Provides semantic search, metadata fetch, citation data,
and open access PDF discovery.

API docs: https://api.semanticscholar.org/api-docs/
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from paper_expert.core.config import PaperExpertConfig
from paper_expert.models.paper import PaperMetadata, PaperSource, SearchResult

logger = logging.getLogger(__name__)

S2_API_BASE = "https://api.semanticscholar.org/graph/v1"
S2_SEARCH_FIELDS = (
    "paperId,externalIds,title,authors,year,venue,abstract,"
    "citationCount,openAccessPdf,referenceCount"
)
S2_DETAIL_FIELDS = S2_SEARCH_FIELDS + ",references,citations"
_MAX_RETRIES = 3
_BACKOFF_BASE = 2.0


class SemanticScholarAdapter:
    """Adapter for the Semantic PaperExpert Academic Graph API."""

    def __init__(self, config: PaperExpertConfig) -> None:
        self.api_key = config.api_keys.semantic_scholar or None
        headers: dict[str, str] = {}
        if self.api_key:
            headers["x-api-key"] = self.api_key
        self._client = httpx.AsyncClient(
            base_url=S2_API_BASE,
            headers=headers,
            timeout=30.0,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def _request(self, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        """Make an API request with exponential backoff on rate limits."""
        for attempt in range(_MAX_RETRIES):
            try:
                resp = await self._client.request(method, url, **kwargs)
                if resp.status_code == 429:
                    wait = _BACKOFF_BASE ** (attempt + 1)
                    logger.warning("S2 rate limit hit, waiting %.1fs", wait)
                    await asyncio.sleep(wait)
                    continue
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPStatusError:
                if attempt < _MAX_RETRIES - 1:
                    await asyncio.sleep(_BACKOFF_BASE ** attempt)
                    continue
                raise
        return {}

    async def search(
        self, query: str, limit: int = 20, year: str | None = None
    ) -> list[SearchResult]:
        """Search for papers by query string.

        Args:
            query: Natural language or keyword search query.
            limit: Max results (capped at 100 by S2).
            year: Year range filter, e.g. "2023-2025" or "2024".
        """
        params: dict[str, Any] = {
            "query": query,
            "limit": min(limit, 100),
            "fields": S2_SEARCH_FIELDS,
        }
        if year:
            params["year"] = year

        data = await self._request("GET", "/paper/search", params=params)
        results: list[SearchResult] = []
        for item in data.get("data", []):
            results.append(self._to_search_result(item))
        return results

    async def get_paper(self, paper_id: str) -> PaperMetadata | None:
        """Fetch full metadata for a paper by S2 paper ID, DOI, or arXiv ID.

        Accepts formats: S2 ID, "DOI:xxx", "ARXIV:xxx", "CorpusId:xxx".
        """
        try:
            data = await self._request(
                "GET", f"/paper/{paper_id}", params={"fields": S2_DETAIL_FIELDS}
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise

        return self._to_metadata(data)

    async def get_references(self, paper_id: str, limit: int = 500) -> list[PaperMetadata]:
        """Get papers that this paper cites (outgoing references)."""
        data = await self._request(
            "GET",
            f"/paper/{paper_id}/references",
            params={"fields": S2_SEARCH_FIELDS, "limit": min(limit, 1000)},
        )
        results: list[PaperMetadata] = []
        for item in data.get("data", []):
            cited = item.get("citedPaper")
            if cited and cited.get("title"):
                results.append(self._to_metadata(cited))
        return results

    async def get_citations(self, paper_id: str, limit: int = 500) -> list[PaperMetadata]:
        """Get papers that cite this paper (incoming citations)."""
        data = await self._request(
            "GET",
            f"/paper/{paper_id}/citations",
            params={"fields": S2_SEARCH_FIELDS, "limit": min(limit, 1000)},
        )
        results: list[PaperMetadata] = []
        for item in data.get("data", []):
            citing = item.get("citingPaper")
            if citing and citing.get("title"):
                results.append(self._to_metadata(citing))
        return results

    # ── Conversion helpers ──────────────────────────────────

    def _to_search_result(self, data: dict[str, Any]) -> SearchResult:
        ext_ids = data.get("externalIds") or {}
        authors = [a.get("name", "") for a in data.get("authors", [])]
        oa_pdf = data.get("openAccessPdf") or {}

        return SearchResult(
            title=data.get("title", ""),
            authors=authors,
            year=data.get("year"),
            venue=data.get("venue"),
            doi=ext_ids.get("DOI"),
            arxiv_id=ext_ids.get("ArXiv"),
            s2_paper_id=data.get("paperId"),
            citation_count=data.get("citationCount", 0),
            abstract=data.get("abstract"),
            open_access_pdf_url=oa_pdf.get("url"),
            source=PaperSource.SEMANTIC_SCHOLAR,
        )

    def _to_metadata(self, data: dict[str, Any]) -> PaperMetadata:
        ext_ids = data.get("externalIds") or {}
        authors = [a.get("name", "") for a in data.get("authors", [])]
        oa_pdf = data.get("openAccessPdf") or {}

        ref_ids: list[str] = []
        for ref in data.get("references", []):
            cited = ref.get("citedPaper", ref)
            if pid := cited.get("paperId"):
                ref_ids.append(pid)

        return PaperMetadata(
            title=data.get("title", ""),
            authors=authors,
            year=data.get("year"),
            venue=data.get("venue"),
            doi=ext_ids.get("DOI"),
            arxiv_id=ext_ids.get("ArXiv"),
            s2_paper_id=data.get("paperId"),
            citation_count=data.get("citationCount", 0),
            abstract=data.get("abstract"),
            open_access_pdf_url=oa_pdf.get("url"),
            references=ref_ids,
            source=PaperSource.SEMANTIC_SCHOLAR,
        )
