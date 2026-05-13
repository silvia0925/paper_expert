"""Monitoring engine -- periodic paper discovery and notification.

Orchestrates: search -> deduplicate -> add -> notify -> log.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable

from paper_expert.adapters.notify import send_all
from paper_expert.core.database import Database
from paper_expert.models.monitor import MonitorResult, MonitorRunResult

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[str], None]


class Monitor:
    """Runs watch topic monitoring cycles."""

    def __init__(
        self,
        db: Database,
        library: Any,
        config: Any,
    ) -> None:
        self.db = db
        self.library = library
        self.config = config

    async def run_all(
        self,
        on_progress: ProgressCallback | None = None,
    ) -> MonitorRunResult:
        def _progress(msg: str) -> None:
            logger.info(msg)
            if on_progress:
                on_progress(msg)

        topics = self.db.list_watch_topics(active_only=True)
        run_at = datetime.now(timezone.utc).isoformat()

        results: list[MonitorResult] = []
        total_found = 0
        total_added = 0

        for topic in topics:
            _progress(
                f"Monitoring: {topic['name']} "
                f"({len(topic['queries'])} queries)"
            )
            result = await self._run_one(topic, on_progress=on_progress)
            results.append(result)
            if result.is_success:
                total_found += result.papers_found
                total_added += result.papers_added
                self.db.touch_watch_topic(topic["id"])
                self.db.add_watch_log(
                    watch_id=topic["id"],
                    papers_found=result.papers_found,
                    papers_added=result.papers_added,
                    notify_status=",".join(
                        k for k, v in result.notify_results.items() if v
                    ),
                    error=None,
                )
            else:
                self.db.add_watch_log(
                    watch_id=topic["id"], error=result.error
                )

        _progress(
            f"Monitor complete: {len(results)} topics, "
            f"{total_found} papers found, {total_added} added"
        )

        return MonitorRunResult(
            run_at=run_at,
            topics_checked=len(topics),
            results=results,
            total_found=total_found,
            total_added=total_added,
        )

    async def run_one(self, watch_id: int) -> MonitorResult:
        topic = self.db.get_watch_topic(watch_id)
        if not topic:
            return MonitorResult(
                watch_id=watch_id,
                error=f"Watch topic {watch_id} not found",
            )
        result = await self._run_one(topic)
        if result.is_success:
            self.db.touch_watch_topic(watch_id)
            self.db.add_watch_log(
                watch_id=watch_id,
                papers_found=result.papers_found,
                papers_added=result.papers_added,
                notify_status=",".join(
                    k for k, v in result.notify_results.items() if v
                ),
                error=None,
            )
        else:
            self.db.add_watch_log(
                watch_id=watch_id, error=result.error
            )
        return result

    async def _run_one(
        self,
        topic: dict[str, Any],
        on_progress: ProgressCallback | None = None,
    ) -> MonitorResult:
        watch_id = topic["id"]
        queries = topic.get("queries", [])
        sources = topic.get("sources") or None
        fetch_limit = topic.get("fetch_limit", 10)
        notify_channels = topic.get("notify_channels") or None

        if not queries:
            return MonitorResult(
                watch_id=watch_id,
                topic_name=topic["name"],
                error="No search queries configured",
            )

        def _progress(msg: str) -> None:
            if on_progress:
                on_progress(msg)

        all_new_papers: list[dict] = []
        papers_found = 0
        papers_added = 0

        for query in queries:
            _progress(f"  Searching: {query[:60]}")
            try:
                results = await self.library.search(
                    query, sources=sources, limit=fetch_limit
                )
            except Exception:
                logger.warning(
                    "Search failed for query: %s",
                    query[:60],
                    exc_info=True,
                )
                continue

            papers_found += len(results)

            for r in results:
                if r.in_library:
                    continue

                try:
                    from paper_expert.models.paper import PaperMetadata

                    metadata = PaperMetadata(
                        title=r.title,
                        authors=r.authors,
                        year=r.year,
                        venue=r.venue,
                        doi=r.doi,
                        arxiv_id=r.arxiv_id,
                        s2_paper_id=r.s2_paper_id,
                        citation_count=r.citation_count,
                        abstract=r.abstract,
                        open_access_pdf_url=r.open_access_pdf_url,
                        source=r.source,
                    )
                    paper = await self.library.add_paper(
                        metadata, auto_classify=True
                    )
                    if paper:
                        papers_added += 1
                        all_new_papers.append({
                            "title": paper.title,
                            "authors": paper.authors,
                            "year": paper.year,
                            "venue": paper.venue,
                            "doi": paper.doi,
                        })
                except Exception:
                    logger.debug(
                        "Failed to add paper: %s",
                        r.title[:60],
                        exc_info=True,
                    )

        notify_results: dict[str, bool] = {}
        if all_new_papers:
            _progress(
                f"  Sending notifications for "
                f"{len(all_new_papers)} new papers"
            )
            try:
                notify_results = await send_all(
                    self.config,
                    topic["name"],
                    all_new_papers,
                    channels=notify_channels,
                )
            except Exception:
                logger.warning(
                    "Notification failed for topic: %s",
                    topic["name"],
                    exc_info=True,
                )

        return MonitorResult(
            watch_id=watch_id,
            topic_name=topic["name"],
            queries_searched=queries,
            papers_found=papers_found,
            papers_added=papers_added,
            new_papers=all_new_papers,
            notify_results=notify_results,
        )
