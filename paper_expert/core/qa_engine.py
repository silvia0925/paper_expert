# -*- coding: utf-8 -*-
"""QA Engine  — question answering over the knowledge base.

Wraps PaperQA2's query capability with scope filtering, confidence assessment,
and summary generation with caching.
"""

from __future__ import annotations

import logging
from typing import Any

from paper_expert.adapters.paperqa import PaperQAAdapter
from paper_expert.core.database import Database
from paper_expert.models.qa import ConfidenceLevel, QAAnswer, QASource

logger = logging.getLogger(__name__)

# Confidence thresholds
_MIN_CONTEXTS_FOR_SUFFICIENT = 2
_HIGH_CONFIDENCE_MIN_SCORE = 0.7
_MEDIUM_CONFIDENCE_MIN_SCORE = 0.4


def parse_scope(scope: str) -> dict[str, str]:
    """Parse a scope string like 'tag:OPC' or 'year:2024-2025'.

    Returns dict with keys like {'tag': 'OPC'} or {'year': '2024-2025'}.
    """
    result: dict[str, str] = {}
    for part in scope.split(","):
        part = part.strip()
        if ":" in part:
            key, value = part.split(":", 1)
            result[key.strip()] = value.strip()
    return result


def _get_scoped_paper_ids(db: Database, scope: dict[str, str]) -> list[int]:
    """Query SQLite for paper IDs matching the scope filters."""
    conditions: list[str] = []
    params: list[Any] = []

    if "tag" in scope:
        conditions.append(
            "p.id IN (SELECT paper_id FROM tags WHERE tag = ?)"
        )
        params.append(scope["tag"])

    if "year" in scope:
        year_str = scope["year"]
        if "-" in year_str:
            parts = year_str.split("-")
            conditions.append("p.year >= ? AND p.year <= ?")
            params.extend([int(parts[0]), int(parts[1])])
        else:
            conditions.append("p.year = ?")
            params.append(int(year_str))

    # Only full-text papers can be queried
    conditions.append("p.state = 'full-text'")

    query = "SELECT p.id FROM papers p"
    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    with db.connection() as conn:
        rows = conn.execute(query, params).fetchall()
        return [r["id"] for r in rows]


def assess_confidence(contexts: list[dict[str, Any]]) -> tuple[ConfidenceLevel, bool]:
    """Assess answer confidence based on retrieved contexts.

    Returns (confidence_level, is_sufficient).
    """
    if not contexts:
        return ConfidenceLevel.LOW, False

    num_contexts = len(contexts)
    scores = [c.get("score", 0.0) for c in contexts]
    avg_score = sum(scores) / len(scores) if scores else 0.0

    if num_contexts < _MIN_CONTEXTS_FOR_SUFFICIENT:
        return ConfidenceLevel.LOW, False

    if avg_score >= _HIGH_CONFIDENCE_MIN_SCORE:
        return ConfidenceLevel.HIGH, True
    elif avg_score >= _MEDIUM_CONFIDENCE_MIN_SCORE:
        return ConfidenceLevel.MEDIUM, True
    else:
        return ConfidenceLevel.LOW, False


def _raw_to_qa_answer(raw: dict[str, Any], db: Database | None = None) -> QAAnswer:
    """Convert raw PaperQA adapter dict to QAAnswer model."""
    if raw.get("error"):
        return QAAnswer(
            answer="",
            question=raw.get("question", ""),
            error=raw["error"],
        )

    # Build sources from contexts
    sources: list[QASource] = []
    contexts = raw.get("contexts", [])
    for ctx in contexts:
        doc_name = ctx.get("doc_name", "")
        # Try to resolve paper_id from doc_name via database
        paper_id = None
        paper_year = None
        if db and doc_name:
            # doc_name is typically the paper title (first 100 chars)
            with db.connection() as conn:
                row = conn.execute(
                    "SELECT id, year FROM papers WHERE title LIKE ? LIMIT 1",
                    (f"{doc_name[:80]}%",),
                ).fetchone()
                if row:
                    paper_id = row["id"]
                    paper_year = row["year"]

        sources.append(QASource(
            paper_id=paper_id,
            paper_title=doc_name,
            year=paper_year,
            passage=ctx.get("text", ""),
            relevance_score=ctx.get("score", 0.0),
        ))

    confidence, is_sufficient = assess_confidence(contexts)

    return QAAnswer(
        answer=raw.get("answer", ""),
        question=raw.get("question", ""),
        sources=sources,
        cost=raw.get("cost", 0.0),
        confidence=confidence,
        is_sufficient=is_sufficient,
    )


class QAEngine:
    """Question-answering engine over the paper knowledge base."""

    def __init__(self, paperqa: PaperQAAdapter, db: Database) -> None:
        self.paperqa = paperqa
        self.db = db

    async def ask(
        self,
        question: str,
        scope: str | None = None,
    ) -> QAAnswer:
        """Ask a question, optionally scoped to a subset of papers.

        Args:
            question: The question to answer.
            scope: Optional scope filter, e.g. "tag:OPC" or "year:2024-2025".

        Returns:
            QAAnswer with answer text, sources, and confidence.
        """
        if not self.paperqa.available:
            return QAAnswer(
                question=question,
                error="PaperQA2 is not available. Install paper-qa and configure a cloud LLM.",
            )

        # TODO: scope filtering via temporary Docs subset
        # For now, scope is noted but queries run against full Docs.
        # Full scope filtering requires building a filtered Docs,
        # which depends on PaperQA2's internal API for doc-level filtering.
        if scope:
            parsed = parse_scope(scope)
            scoped_ids = _get_scoped_paper_ids(self.db, parsed)
            logger.info(
                "Scope filter matched %d papers (full filtering pending)",
                len(scoped_ids),
            )
            if not scoped_ids:
                return QAAnswer(
                    question=question,
                    error=f"No full-text papers match scope '{scope}'.",
                )

        raw = await self.paperqa.query(question)
        return _raw_to_qa_answer(raw, db=self.db)

    async def summarize_paper(self, paper_id: int) -> str:
        """Generate or retrieve a cached summary for a paper.

        Returns the summary text.
        """
        # Check cache first
        cached = self.db.get_summary(paper_id)
        if cached:
            return cached["summary_text"]

        # Get paper info
        paper = self.db.get_paper(paper_id)
        if not paper:
            return "Paper not found."

        if paper["state"] != "full-text":
            return "Cannot summarize metadata-only papers. Provide a PDF first."

        title = paper["title"]
        summary = await self.paperqa.summarize(title)

        # Cache the summary
        model_used = None
        if self.paperqa.config and self.paperqa.config.llm.cloud_model:
            model_used = self.paperqa.config.llm.cloud_model
        self.db.save_summary(paper_id, summary, model_used)

        return summary
