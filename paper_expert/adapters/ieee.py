"""IEEE Xplore API adapter.

Optional source for semiconductor/lithography papers. Requires API key.
Rate limit: 200 requests/month on free tier.

API docs: https://developer.ieee.org/
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from paper_expert.core.config import PaperExpertConfig
from paper_expert.models.paper import PaperSource, SearchResult

logger = logging.getLogger(__name__)

IEEE_API_BASE = "https://ieeexploreapi.ieee.org/api/v1/search/articles"


class IEEEAdapter:
    """Adapter for the IEEE Xplore API."""

    def __init__(self, config: PaperExpertConfig) -> None:
        self.api_key = config.api_keys.ieee_xplore
        self._client = httpx.AsyncClient(timeout=30.0)

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    async def close(self) -> None:
        await self._client.aclose()

    async def search(
        self, query: str, limit: int = 20, year: str | None = None
    ) -> list[SearchResult]:
        """Search IEEE Xplore for papers.

        Args:
            query: Search query.
            limit: Max results (max 200).
            year: Year range, e.g. "2023-2025".
        """
        if not self.available:
            logger.warning("IEEE Xplore API key not configured, skipping search")
            return []

        params: dict[str, Any] = {
            "apikey": self.api_key,
            "querytext": query,
            "max_records": min(limit, 200),
            "sort_field": "article_title",
            "sort_order": "asc",
        }
        if year:
            parts = year.split("-")
            if len(parts) == 2:
                params["start_year"] = parts[0]
                params["end_year"] = parts[1]
            elif len(parts) == 1:
                params["start_year"] = parts[0]
                params["end_year"] = parts[0]

        try:
            resp = await self._client.get(IEEE_API_BASE, params=params)
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                logger.warning("IEEE Xplore monthly rate limit reached")
            else:
                logger.error("IEEE Xplore API error: %s", e)
            return []

        results: list[SearchResult] = []
        for article in data.get("articles", []):
            results.append(self._to_search_result(article))
        return results

    def _to_search_result(self, article: dict[str, Any]) -> SearchResult:
        authors_data = article.get("authors", {}).get("authors", [])
        authors = [a.get("full_name", "") for a in authors_data if a.get("full_name")]

        doi = article.get("doi")
        year_str = article.get("publication_year")
        year = int(year_str) if year_str else None

        return SearchResult(
            title=article.get("title", ""),
            authors=authors,
            year=year,
            venue=article.get("publication_title"),
            doi=doi,
            citation_count=article.get("citing_paper_count", 0),
            abstract=article.get("abstract"),
            source=PaperSource.IEEE,
        )
