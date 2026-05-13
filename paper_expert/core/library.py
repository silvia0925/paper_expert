"""Knowledge Base Library �?the central orchestrator.

Ties together Database, PaperQA adapter, search aggregator, PDF fetcher,
and classifier into a unified interface.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from paper_expert.adapters.paperqa import PaperQAAdapter
from paper_expert.adapters.semantic_scholar import SemanticScholarAdapter
from paper_expert.core.config import PaperExpertConfig
from paper_expert.core.database import Database
from paper_expert.core.pdf_fetcher import PDFFetcher
from paper_expert.core.search import SearchAggregator
from paper_expert.models.paper import (
    Paper,
    PaperMetadata,
    PaperSource,
    PaperState,
    SearchResult,
)

logger = logging.getLogger(__name__)


class Library:
    """Central knowledge base manager.

    Orchestrates all components: storage, search, parsing, classification.
    """

    def __init__(self, config: PaperExpertConfig | None = None) -> None:
        self.config = config or PaperExpertConfig.load()
        self._ensure_dirs()

        self.db = Database(self.config.library_path / "metadata.db")
        self.paperqa = PaperQAAdapter(self.config)
        self.search_engine = SearchAggregator(self.config)
        self.pdf_fetcher = PDFFetcher(
            pdf_dir=self.config.library_path / "pdfs",
            unpaywall_email=self.config.api_keys.unpaywall_email,
            config=self.config,
        )
        self._s2 = SemanticScholarAdapter(self.config)

    def _ensure_dirs(self) -> None:
        """Create library directory structure."""
        base = self.config.library_path
        for subdir in ("pdfs", "parsed", "vectors"):
            (base / subdir).mkdir(parents=True, exist_ok=True)

    async def close(self) -> None:
        """Clean up async resources."""
        await self.search_engine.close()
        await self.pdf_fetcher.close()
        await self._s2.close()

    # ── Search ──────────────────────────────────────────────

    async def search(
        self,
        query: str,
        sources: list[str] | None = None,
        limit: int | None = None,
        year: str | None = None,
    ) -> list[SearchResult]:
        """Search for papers across configured sources.

        Returns deduplicated results with library membership marked.
        """
        results = await self.search_engine.search(
            query=query, sources=sources, limit=limit, year=year
        )

        # Mark which results are already in the library
        for r in results:
            r.in_library = self.db.paper_exists(doi=r.doi, title=r.title)

        return results

    # ── Add Paper ──────────────────────────────────────────

    async def add_paper(
        self,
        metadata: PaperMetadata,
        pdf_path: Path | None = None,
        auto_classify: bool = True,
    ) -> Paper | None:
        """Add a paper to the knowledge base.

        Full flow: store metadata �?fetch PDF �?parse/vectorize �?classify �?save citations.
        """
        # Check for duplicates
        if metadata.doi and self.db.paper_exists(doi=metadata.doi):
            existing = self.db.get_paper_by_doi(metadata.doi)
            if existing:
                logger.info("Paper already in library: %s", metadata.title[:60])
                return Paper.from_db_row(existing)

        # Step 1: Classify L0 first (needed for PDF folder organization)
        l0_category: str | None = None
        if auto_classify:
            try:
                from paper_expert.core.classifier import classify_l0

                l0_tags = classify_l0(metadata.title, metadata.abstract, self.config.domain)
                l0_category = l0_tags[0] if l0_tags else None
            except Exception:
                logger.warning("L0 pre-classification failed for '%s' — "
                               "paper will be added without auto-category. "
                               "Run 'paper-expert lib classify' later to retry.",
                               metadata.title[:60], exc_info=True)

        # Step 2: Attempt PDF acquisition if not provided (into category subfolder)
        if pdf_path is None:
            pdf_path = await self.pdf_fetcher.fetch(metadata, category=l0_category)

        # Step 3: Determine state
        state = PaperState.FULL_TEXT if pdf_path else PaperState.METADATA_ONLY

        # Step 4: Parse and vectorize if we have a PDF
        if pdf_path and self.paperqa.available:
            success = await self.paperqa.add_document(
                pdf_path, doc_name=metadata.title[:100]
            )
            if not success:
                logger.warning("Failed to vectorize PDF, keeping as metadata-only")
                state = PaperState.METADATA_ONLY

        # Step 5: Store in database
        paper_id = self.db.add_paper(
            title=metadata.title,
            doi=metadata.doi,
            authors=metadata.authors,
            year=metadata.year,
            venue=metadata.venue,
            abstract=metadata.abstract,
            source=metadata.source.value,
            state=state.value,
            arxiv_id=metadata.arxiv_id,
            s2_paper_id=metadata.s2_paper_id,
            citation_count=metadata.citation_count,
            pdf_path=str(pdf_path) if pdf_path else None,
        )

        # Step 6: Auto-classify (full �?L0 already done above, this adds to DB + L1)
        if auto_classify:
            try:
                from paper_expert.core.classifier import classify_paper

                classify_paper(self.db, paper_id, metadata, self.config.domain)
            except Exception:
                logger.warning("Auto-classification (L1) failed for paper #%d '%s' — "
                               "run 'paper-expert lib classify' to retry later.",
                               paper_id, metadata.title[:60], exc_info=True)

        # Step 6: Save citation relationships
        await self._save_citations(paper_id, metadata)

        # Return the full Paper object
        row = self.db.get_paper(paper_id)
        if row:
            tags = self.db.get_tags(paper_id)
            return Paper.from_db_row(row, tags)
        return None

    async def add_by_identifier(
        self, identifier: str, pdf_path: Path | None = None
    ) -> Paper | None:
        """Add a paper by identifier string (DOI, arXiv ID, or S2 ID).

        Resolves metadata from Semantic PaperExpert, then calls add_paper.
        """
        # Normalize identifier
        if identifier.startswith("doi:"):
            s2_query = f"DOI:{identifier[4:]}"
        elif identifier.startswith("arxiv:"):
            s2_query = f"ARXIV:{identifier[6:]}"
        else:
            s2_query = identifier

        metadata = await self._s2.get_paper(s2_query)
        if not metadata:
            logger.error("Could not resolve identifier: %s", identifier)
            return None

        return await self.add_paper(metadata, pdf_path=pdf_path)

    async def upgrade_to_fulltext(self, paper_id: int, pdf_path: Path) -> bool:
        """Upgrade a metadata-only paper to full-text by providing a PDF."""
        paper_row = self.db.get_paper(paper_id)
        if not paper_row:
            logger.error("Paper not found: %d", paper_id)
            return False

        if paper_row["state"] == PaperState.FULL_TEXT.value:
            logger.info("Paper already has full text")
            return True

        if self.paperqa.available:
            success = await self.paperqa.add_document(
                pdf_path, doc_name=paper_row["title"][:100]
            )
            if not success:
                return False

        self.db.update_paper(
            paper_id,
            state=PaperState.FULL_TEXT.value,
            pdf_path=str(pdf_path),
        )
        return True

    # ── List / Get ──────────────────────────────────────────

    def list_papers(
        self,
        state: str | None = None,
        year: int | None = None,
        tag: str | None = None,
        sort_by: str = "date_added",
        limit: int = 100,
        offset: int = 0,
    ) -> list[Paper]:
        """List papers with optional filters."""
        rows = self.db.list_papers(
            state=state, year=year, tag=tag, sort_by=sort_by, limit=limit, offset=offset
        )
        papers: list[Paper] = []
        for row in rows:
            tags = self.db.get_tags(row["id"])
            papers.append(Paper.from_db_row(row, tags))
        return papers

    def get_paper(self, paper_id: int) -> Paper | None:
        """Get a single paper by ID."""
        row = self.db.get_paper(paper_id)
        if not row:
            return None
        tags = self.db.get_tags(paper_id)
        return Paper.from_db_row(row, tags)

    # ── Statistics ──────────────────────────────────────────

    def get_stats(self) -> dict[str, Any]:
        """Get knowledge base statistics."""
        stats = self.db.get_stats()

        # Add storage info
        pdf_dir = self.config.library_path / "pdfs"
        if pdf_dir.exists():
            total_size = sum(f.stat().st_size for f in pdf_dir.rglob("*") if f.is_file())
            stats["storage_mb"] = round(total_size / (1024 * 1024), 1)
        else:
            stats["storage_mb"] = 0

        return stats

    # ── Citation helpers ──────────────────────────────────

    async def _save_citations(self, paper_id: int, metadata: PaperMetadata) -> None:
        """Fetch and store citation relationships for a paper."""
        if not metadata.s2_paper_id:
            return

        try:
            refs = await self._s2.get_references(metadata.s2_paper_id, limit=100)
        except Exception:
            logger.warning("Failed to fetch citation references for '%s' — "
                           "citations not saved for this paper.",
                           metadata.title[:60], exc_info=True)
            return

        for ref in refs:
            # Find or create the cited paper in database
            cited_row = None
            if ref.doi:
                cited_row = self.db.get_paper_by_doi(ref.doi)
            if not cited_row and ref.s2_paper_id:
                cited_row = self.db.get_paper_by_s2_id(ref.s2_paper_id)

            if not cited_row:
                # Create metadata-only stub
                cited_id = self.db.add_paper(
                    title=ref.title,
                    doi=ref.doi,
                    authors=ref.authors,
                    year=ref.year,
                    venue=ref.venue,
                    abstract=ref.abstract,
                    source=PaperSource.SEMANTIC_SCHOLAR.value,
                    state=PaperState.METADATA_ONLY.value,
                    arxiv_id=ref.arxiv_id,
                    s2_paper_id=ref.s2_paper_id,
                    citation_count=ref.citation_count,
                )
            else:
                cited_id = cited_row["id"]

            self.db.add_citation(paper_id, cited_id)

    # ── QA (Phase 2) ──────────────────────────────────────

    async def ask(
        self,
        question: str,
        scope: str | None = None,
        auto_fetch: bool = False,
        fetch_limit: int = 5,
        max_iterations: int = 3,
        on_progress: Any = None,
    ) -> Any:
        """Ask a question against the knowledge base.

        Args:
            question: The research question.
            scope: Optional scope filter, e.g. "tag:OPC" or "year:2024-2025".
            auto_fetch: If True, automatically fetch new papers when answer is insufficient.
            fetch_limit: Max papers to fetch per auto-fetch iteration.
            max_iterations: Max auto-fetch iterations.
            on_progress: Optional progress callback for auto-fetch.

        Returns:
            QAAnswer from the QA engine.
        """
        from paper_expert.core.qa_engine import QAEngine

        qa = QAEngine(self.paperqa, self.db)

        if auto_fetch:
            from paper_expert.core.auto_fetch import AutoFetcher

            fetcher = AutoFetcher(qa, self)
            return await fetcher.ask_with_fetch(
                question,
                scope=scope,
                fetch_limit=fetch_limit,
                max_iterations=max_iterations,
                on_progress=on_progress,
            )

        return await qa.ask(question, scope=scope)

    async def get_summary(self, paper_id: int) -> str | None:
        """Get or generate a summary for a paper.

        Returns the summary text, or None if the paper doesn't exist.
        """
        paper = self.db.get_paper(paper_id)
        if not paper:
            return None

        from paper_expert.core.qa_engine import QAEngine

        qa = QAEngine(self.paperqa, self.db)
        return await qa.summarize_paper(paper_id)

    # ── Literature Review (Phase 3) ──────────────────────

    async def generate_review(
        self,
        topic: str,
        scope: str | None = None,
        auto_fetch: bool = False,
        refresh: bool = False,
        on_progress: Any = None,
    ) -> str:
        """Generate a literature review for a topic."""
        from paper_expert.core.review_engine import ReviewEngine

        engine = ReviewEngine(self.db, self.config)
        return await engine.generate(
            topic=topic, scope=scope, auto_fetch=auto_fetch,
            refresh=refresh, library=self, on_progress=on_progress,
        )

    async def suggest_directions(
        self,
        topic: str,
        include_trends: bool = True,
    ) -> Any:
        """Analyze topic and suggest research directions."""
        from paper_expert.core.direction_advisor import DirectionAdvisor

        advisor = DirectionAdvisor(self.db, self.config)
        return await advisor.analyze(topic, include_trends=include_trends)

    async def build_expertise(
        self,
        topic: str,
        update: bool = False,
        ask: str | None = None,
        on_progress: Any = None,
    ) -> str:
        """Build domain expertise or ask an expert question."""
        from paper_expert.core.domain_expert import DomainExpert

        expert = DomainExpert(self.db, self.config)

        if ask:
            return await expert.ask_expert(topic, ask)

        return await expert.build(topic, update=update, on_progress=on_progress)

    # ── Monitor (Watch Topics) ────────────────────────────

    async def run_monitor(
        self,
        watch_id: int | None = None,
        on_progress: Any = None,
    ) -> Any:
        from paper_expert.core.monitor import Monitor

        monitor = Monitor(self.db, self, self.config)
        if watch_id is not None:
            return await monitor.run_one(watch_id)
        return await monitor.run_all(on_progress=on_progress)

    def list_watch_topics(self, active_only: bool = False) -> list[dict]:
        return self.db.list_watch_topics(active_only=active_only)

    def add_watch_topic(
        self,
        name: str,
        queries: list[str],
        sources: list[str] | None = None,
        fetch_limit: int = 10,
        notify_channels: list[str] | None = None,
    ) -> int:
        return self.db.add_watch_topic(
            name=name,
            queries=queries,
            sources=sources,
            fetch_limit=fetch_limit,
            notify_channels=notify_channels,
        )

    def update_watch_topic(self, watch_id: int, **kwargs: Any) -> None:
        self.db.update_watch_topic(watch_id, **kwargs)

    def delete_watch_topic(self, watch_id: int) -> None:
        self.db.delete_watch_topic(watch_id)

    def get_watch_topic(self, watch_id: int) -> dict | None:
        return self.db.get_watch_topic(watch_id)

    def get_watch_logs(self, watch_id: int, limit: int = 20) -> list[dict]:
        return self.db.get_watch_logs(watch_id, limit=limit)
