"""Research Direction Advisor �?identify gaps and suggest new directions.

Analyzes the knowledge base to build a method x problem matrix,
detect trends, and generate evidence-based research suggestions.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

from paper_expert.core.config import PaperExpertConfig
from paper_expert.core.database import Database
from paper_expert.core.llm import llm_chat_json
from paper_expert.models.review import (
    DirectionReport,
    NoveltyLevel,
    ResearchSuggestion,
    TrendEntry,
)

logger = logging.getLogger(__name__)


class DirectionAdvisor:
    """Analyzes knowledge base to suggest research directions."""

    def __init__(self, db: Database, config: PaperExpertConfig) -> None:
        self.db = db
        self.config = config

    async def analyze(
        self,
        topic: str,
        include_trends: bool = True,
    ) -> DirectionReport:
        """Analyze a topic and generate research direction suggestions.

        Returns a DirectionReport with suggestions, trends, and matrix gaps.
        """
        # Retrieve relevant papers
        papers = self._get_topic_papers(topic)
        if not papers:
            return DirectionReport(
                topic=topic,
                suggestions=[ResearchSuggestion(
                    title="Insufficient data",
                    description=f"No papers found for '{topic}'. Add papers first.",
                    novelty=NoveltyLevel.UNEXPLORED,
                )],
            )

        # Build method x problem matrix
        matrix, methods, problems = await self._build_matrix(topic, papers)

        # Identify gaps
        gaps = self._find_gaps(matrix, methods, problems)

        # Trend analysis
        trends: list[TrendEntry] = []
        if include_trends:
            trends = self._analyze_trends(papers)

        # Generate suggestions via LLM
        suggestions = await self._generate_suggestions(topic, papers, gaps, trends)

        return DirectionReport(
            topic=topic,
            suggestions=suggestions,
            trends=trends,
            matrix_gaps=gaps,
            paper_count_analyzed=len(papers),
        )

    def _get_topic_papers(self, topic: str) -> list[dict[str, Any]]:
        """Get papers related to a topic from the database."""
        with self.db.connection() as conn:
            pattern = f"%{topic}%"
            rows = conn.execute(
                """SELECT p.*, GROUP_CONCAT(t.tag, ', ') as all_tags
                   FROM papers p
                   LEFT JOIN tags t ON t.paper_id = p.id
                   WHERE p.title LIKE ? OR p.abstract LIKE ?
                   GROUP BY p.id
                   ORDER BY p.citation_count DESC
                   LIMIT 50""",
                (pattern, pattern),
            ).fetchall()
            return [dict(r) for r in rows]

    async def _build_matrix(
        self, topic: str, papers: list[dict[str, Any]]
    ) -> tuple[dict[str, dict[str, list[int]]], list[str], list[str]]:
        """Build a method x problem co-occurrence matrix using LLM."""
        from paper_expert.core.review_engine import _paper_summary_block

        paper_block = _paper_summary_block(papers[:20])

        messages = [
            {"role": "system", "content": "You are a research method analyst. Output valid JSON only."},
            {"role": "user", "content": (
                f"Topic: {topic}\n\n"
                f"Papers:\n{paper_block}\n\n"
                "Analyze these papers and extract:\n"
                '1. "methods": list of distinct methods/techniques used (e.g., "CNN", "GAN", "ILT")\n'
                '2. "problems": list of distinct problems/tasks addressed (e.g., "OPC", "mask optimization")\n'
                '3. "assignments": list of objects with "paper_index", "method", "problem"\n\n'
                "Return as JSON object."
            )},
        ]
        result = await llm_chat_json(messages, config=self.config)

        methods = result.get("methods", [])
        problems = result.get("problems", [])
        assignments = result.get("assignments", [])

        # Build matrix
        matrix: dict[str, dict[str, list[int]]] = {m: {p: [] for p in problems} for m in methods}
        for a in assignments:
            m = a.get("method", "")
            p = a.get("problem", "")
            idx = a.get("paper_index", 0)
            if m in matrix and p in matrix.get(m, {}):
                matrix[m][p].append(idx)

        return matrix, methods, problems

    def _find_gaps(
        self,
        matrix: dict[str, dict[str, list[int]]],
        methods: list[str],
        problems: list[str],
    ) -> list[str]:
        """Find empty cells in the method x problem matrix."""
        gaps: list[str] = []
        for method in methods:
            for problem in problems:
                if not matrix.get(method, {}).get(problem, []):
                    gaps.append(f"{method} + {problem}")
        return gaps

    def _analyze_trends(self, papers: list[dict[str, Any]]) -> list[TrendEntry]:
        """Detect trends by analyzing publication year distribution."""
        # Group by tags and year
        tag_year: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))

        for p in papers:
            year = p.get("year")
            tags_str = p.get("all_tags", "") or ""
            if not year:
                continue
            for tag in tags_str.split(", "):
                tag = tag.strip()
                if tag:
                    tag_year[tag][year] += 1

        trends: list[TrendEntry] = []
        for tag, years in tag_year.items():
            if len(years) < 2:
                continue
            sorted_years = sorted(years.keys())
            year_range = f"{sorted_years[0]}-{sorted_years[-1]}"
            total = sum(years.values())

            # Simple trend detection: compare first half vs second half
            mid = sorted_years[len(sorted_years) // 2]
            early = sum(c for y, c in years.items() if y <= mid)
            late = sum(c for y, c in years.items() if y > mid)

            if late > early * 1.5:
                direction = "rising"
                desc = f"Gaining traction: {early} papers before {mid}, {late} after"
            elif early > late * 1.5:
                direction = "declining"
                desc = f"Declining: {early} papers before {mid}, {late} after"
            else:
                direction = "stable"
                desc = f"Steady output: {total} papers across {year_range}"

            trends.append(TrendEntry(
                method_or_topic=tag,
                direction=direction,
                paper_count=total,
                year_range=year_range,
                description=desc,
            ))

        # Sort: rising first, then declining, then stable
        order = {"rising": 0, "declining": 1, "stable": 2}
        trends.sort(key=lambda t: order.get(t.direction, 3))
        return trends

    async def _generate_suggestions(
        self,
        topic: str,
        papers: list[dict[str, Any]],
        gaps: list[str],
        trends: list[TrendEntry],
    ) -> list[ResearchSuggestion]:
        """Generate research direction suggestions using LLM."""
        gaps_text = "\n".join(f"- {g}" for g in gaps[:15])
        trends_text = "\n".join(
            f"- [{t.direction}] {t.method_or_topic}: {t.description}"
            for t in trends[:10]
        )

        messages = [
            {"role": "system", "content": "You are a research advisor. Output valid JSON only."},
            {"role": "user", "content": (
                f"Topic: {topic}\n"
                f"Papers analyzed: {len(papers)}\n\n"
                f"Unexplored method+problem combinations:\n{gaps_text}\n\n"
                f"Detected trends:\n{trends_text}\n\n"
                "Based on the gaps and trends, suggest 3-5 promising research directions.\n"
                "Return a JSON array, each with:\n"
                '- "title": concise direction title\n'
                '- "description": 2-3 sentence description\n'
                '- "reasoning": why this is promising\n'
                '- "novelty": "unexplored" or "emerging" or "active"\n'
                '- "evidence": list of relevant gap or trend names'
            )},
        ]
        result = await llm_chat_json(messages, config=self.config)

        suggestions: list[ResearchSuggestion] = []
        items = result if isinstance(result, list) else []
        for item in items:
            novelty_str = item.get("novelty", "emerging")
            try:
                novelty = NoveltyLevel(novelty_str)
            except ValueError:
                novelty = NoveltyLevel.EMERGING

            suggestions.append(ResearchSuggestion(
                title=item.get("title", ""),
                description=item.get("description", ""),
                evidence=item.get("evidence", []),
                novelty=novelty,
                reasoning=item.get("reasoning", ""),
            ))

        return suggestions
