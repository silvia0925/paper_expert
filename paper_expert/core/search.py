"""Multi-source search aggregator.

Queries configured sources in parallel, deduplicates by DOI,
and merges metadata (Semantic PaperExpert primary, OpenAlex supplementary).
"""

from __future__ import annotations

import asyncio
import logging

from paper_expert.adapters.arxiv import ArxivAdapter
from paper_expert.adapters.ieee import IEEEAdapter
from paper_expert.adapters.openalex import OpenAlexAdapter
from paper_expert.adapters.semantic_scholar import SemanticScholarAdapter
from paper_expert.core.config import PaperExpertConfig
from paper_expert.models.paper import SearchResult

logger = logging.getLogger(__name__)


class SearchAggregator:
    """Aggregates paper search results across multiple sources."""

    def __init__(self, config: PaperExpertConfig) -> None:
        self.config = config
        self._s2 = SemanticScholarAdapter(config)
        self._openalex = OpenAlexAdapter(mailto=config.api_keys.unpaywall_email)
        self._arxiv = ArxivAdapter()
        self._ieee = IEEEAdapter(config)

    async def close(self) -> None:
        await asyncio.gather(
            self._s2.close(),
            self._openalex.close(),
            self._arxiv.close(),
            self._ieee.close(),
        )

    async def search(
        self,
        query: str,
        sources: list[str] | None = None,
        limit: int | None = None,
        year: str | None = None,
    ) -> list[SearchResult]:
        """Search across configured sources and return deduplicated results.

        Args:
            query: Search query string.
            sources: List of source names to search. Defaults to config.
            limit: Max results per source.
            year: Year filter (e.g., "2024" or "2023-2025").
        """
        if sources is None:
            sources = self.config.search.default_sources
        if limit is None:
            limit = self.config.search.default_limit

        tasks: list[asyncio.Task[list[SearchResult]]] = []
        source_names: list[str] = []

        for source in sources:
            coro = self._search_source(source, query, limit, year)
            if coro is not None:
                tasks.append(asyncio.create_task(coro))
                source_names.append(source)

        if not tasks:
            return []

        raw_results = await asyncio.gather(*tasks, return_exceptions=True)

        all_results: list[SearchResult] = []
        for name, result in zip(source_names, raw_results):
            if isinstance(result, Exception):
                logger.error("Search failed for source %s: %s", name, result)
                continue
            all_results.extend(result)

        return self._deduplicate(all_results)

    async def _search_source(
        self, source: str, query: str, limit: int, year: str | None
    ) -> list[SearchResult]:
        """Dispatch search to the appropriate adapter."""
        match source:
            case "semantic_scholar":
                return await self._s2.search(query, limit=limit, year=year)
            case "openalex":
                year_int = int(year.split("-")[0]) if year else None
                return await self._openalex.search(query, limit=limit, year=year_int)
            case "arxiv":
                return await self._arxiv.search(query, limit=limit)
            case "ieee":
                return await self._ieee.search(query, limit=limit, year=year)
            case _:
                logger.warning("Unknown search source: %s", source)
                return []

    def _deduplicate(self, results: list[SearchResult]) -> list[SearchResult]:
        """Deduplicate results by DOI, preferring Semantic PaperExpert entries."""
        seen_dois: dict[str, SearchResult] = {}
        seen_titles: set[str] = set()
        unique: list[SearchResult] = []

        # Sort so Semantic PaperExpert results come first (preferred source)
        results.sort(key=lambda r: r.source != "semantic_scholar")

        for r in results:
            if r.doi and r.doi in seen_dois:
                # Merge: supplement missing fields from duplicate
                existing = seen_dois[r.doi]
                if not existing.abstract and r.abstract:
                    existing.abstract = r.abstract
                if not existing.open_access_pdf_url and r.open_access_pdf_url:
                    existing.open_access_pdf_url = r.open_access_pdf_url
                continue

            title_key = r.title.lower().strip()
            if title_key in seen_titles:
                continue

            if r.doi:
                seen_dois[r.doi] = r
            seen_titles.add(title_key)
            unique.append(r)

        return unique
