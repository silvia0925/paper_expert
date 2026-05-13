"""Literature Review Engine �?multi-stage pipeline for generating structured reviews.

Pipeline stages:
1. Topic analysis �?keywords + sub-themes
2. Paper retrieval �?relevant papers from knowledge base
3. Paper grouping �?cluster by methodology/theme
4. Per-group analysis �?extract arguments, compare methods
5. Cross-group synthesis �?agreements, contradictions, trends
6. Document assembly �?final Markdown review
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable

from paper_expert.core.config import PaperExpertConfig
from paper_expert.core.database import Database
from paper_expert.core.llm import llm_chat, llm_chat_json

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[str], None]


def _paper_summary_block(papers: list[dict[str, Any]]) -> str:
    """Format paper list into a compact text block for LLM prompts."""
    lines: list[str] = []
    for i, p in enumerate(papers, 1):
        authors = p.get("authors_json", "[]")
        if isinstance(authors, str):
            import json as _json
            authors = _json.loads(authors)
        first_author = authors[0] if authors else "Unknown"
        title = p.get("title", "Untitled")
        year = p.get("year", "?")
        abstract = (p.get("abstract") or "")[:300]
        lines.append(f"[{i}] {title} ({first_author} et al., {year})")
        if abstract:
            lines.append(f"    Abstract: {abstract}...")
        lines.append("")
    return "\n".join(lines)


class ReviewEngine:
    """Generates structured literature reviews via a multi-stage LLM pipeline."""

    def __init__(self, db: Database, config: PaperExpertConfig) -> None:
        self.db = db
        self.config = config

    async def generate(
        self,
        topic: str,
        scope: str | None = None,
        auto_fetch: bool = False,
        refresh: bool = False,
        library: Any = None,  # Library (avoid circular import)
        on_progress: ProgressCallback | None = None,
    ) -> str:
        """Generate a literature review for a topic.

        Returns Markdown review text.
        """
        def _progress(msg: str) -> None:
            if on_progress:
                on_progress(msg)

        # Check cache
        if not refresh:
            cached = self.db.get_review(topic, scope)
            if cached:
                _progress("Returning cached review")
                return cached["review_text"]

        # Stage 1: Topic analysis
        _progress("Stage 1/6: Analyzing topic...")
        analysis = await self._stage1_topic_analysis(topic)

        # Stage 2: Paper retrieval
        _progress("Stage 2/6: Retrieving relevant papers...")
        papers = self._stage2_retrieve_papers(topic, scope, analysis)

        # Auto-fetch if too few papers
        if auto_fetch and len(papers) < 5 and library:
            _progress(f"Only {len(papers)} papers found. Auto-fetching more...")
            keywords = analysis.get("keywords", [topic])
            for kw in keywords[:3]:
                try:
                    results = await library.search(kw, limit=5)
                    for r in results:
                        if not r.in_library:
                            from paper_expert.models.paper import PaperMetadata
                            meta = PaperMetadata(
                                title=r.title, authors=r.authors, year=r.year,
                                venue=r.venue, doi=r.doi, arxiv_id=r.arxiv_id,
                                s2_paper_id=r.s2_paper_id, citation_count=r.citation_count,
                                abstract=r.abstract, open_access_pdf_url=r.open_access_pdf_url,
                                source=r.source,
                            )
                            await library.add_paper(meta, auto_classify=True)
                except Exception:
                    logger.warning("Auto-fetch failed for keyword '%s' — skipping.", kw, exc_info=True)
            # Re-retrieve after fetching
            papers = self._stage2_retrieve_papers(topic, scope, analysis)

        if not papers:
            return f"No relevant papers found for topic '{topic}' in the knowledge base."

        _progress(f"Found {len(papers)} relevant papers")
        paper_block = _paper_summary_block(papers)

        # Stage 3: Paper grouping
        _progress("Stage 3/6: Grouping papers by methodology...")
        groups = await self._stage3_group_papers(topic, paper_block, papers)

        # Stage 4: Per-group analysis
        _progress("Stage 4/6: Analyzing each group...")
        group_analyses: list[dict[str, Any]] = []
        for group in groups:
            _progress(f"  Analyzing: {group.get('name', 'group')}...")
            analysis_result = await self._stage4_analyze_group(topic, group, papers)
            group_analyses.append(analysis_result)

        # Stage 5: Cross-group synthesis
        _progress("Stage 5/6: Synthesizing across groups...")
        synthesis = await self._stage5_synthesize(topic, group_analyses)

        # Stage 6: Document assembly
        _progress("Stage 6/6: Assembling review document...")
        review_text = await self._stage6_assemble(topic, papers, group_analyses, synthesis)

        # Cache
        model = self.config.llm.cloud_model
        self.db.save_review(topic, review_text, paper_count=len(papers), scope=scope, model_used=model)
        _progress("Review complete!")

        return review_text

    # ── Stage implementations ──────────────────────────────

    async def _stage1_topic_analysis(self, topic: str) -> dict[str, Any]:
        """Expand topic into keywords and sub-themes."""
        messages = [
            {"role": "system", "content": "You are a research topic analyst. Output valid JSON only."},
            {"role": "user", "content": (
                f"Analyze the research topic: '{topic}'\n\n"
                "Return a JSON object with:\n"
                '- "keywords": list of 5-8 search keywords/phrases\n'
                '- "sub_themes": list of 3-5 sub-themes within this topic\n'
                '- "scope_description": 1-2 sentence description of what this topic covers'
            )},
        ]
        result = await llm_chat_json(messages, config=self.config)
        if not result:
            return {"keywords": [topic], "sub_themes": [topic], "scope_description": topic}
        return result

    def _stage2_retrieve_papers(
        self, topic: str, scope: str | None, analysis: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Retrieve relevant papers from the knowledge base."""
        keywords = analysis.get("keywords", [topic])
        all_keywords = [topic] + keywords

        # Search by title/abstract keyword match in SQLite
        found_ids: set[int] = set()
        papers: list[dict[str, Any]] = []

        with self.db.connection() as conn:
            for kw in all_keywords:
                pattern = f"%{kw}%"
                rows = conn.execute(
                    "SELECT * FROM papers WHERE (title LIKE ? OR abstract LIKE ?) LIMIT 50",
                    (pattern, pattern),
                ).fetchall()
                for r in rows:
                    if r["id"] not in found_ids:
                        found_ids.add(r["id"])
                        papers.append(dict(r))

        # Apply scope filters
        if scope:
            papers = self._apply_scope(papers, scope)

        # Sort by citation count descending
        papers.sort(key=lambda p: p.get("citation_count", 0), reverse=True)
        return papers[:30]  # Cap at 30 papers for review

    def _apply_scope(self, papers: list[dict[str, Any]], scope: str) -> list[dict[str, Any]]:
        """Filter papers by scope string."""
        from paper_expert.core.qa_engine import parse_scope
        parsed = parse_scope(scope)

        filtered = papers
        if "year" in parsed:
            year_str = parsed["year"]
            if "-" in year_str:
                y1, y2 = year_str.split("-")
                filtered = [p for p in filtered if p.get("year") and int(y1) <= p["year"] <= int(y2)]
            else:
                y = int(year_str)
                filtered = [p for p in filtered if p.get("year") == y]

        if "tag" in parsed:
            tag = parsed["tag"]
            tag_paper_ids = set()
            with self.db.connection() as conn:
                rows = conn.execute("SELECT paper_id FROM tags WHERE tag = ?", (tag,)).fetchall()
                tag_paper_ids = {r["paper_id"] for r in rows}
            filtered = [p for p in filtered if p["id"] in tag_paper_ids]

        return filtered

    async def _stage3_group_papers(
        self, topic: str, paper_block: str, papers: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Group papers by methodology/theme."""
        messages = [
            {"role": "system", "content": "You are a research paper classifier. Output valid JSON only."},
            {"role": "user", "content": (
                f"Topic: {topic}\n\n"
                f"Papers:\n{paper_block}\n\n"
                "Group these papers into 3-6 methodology/theme clusters.\n"
                "Return a JSON array of groups, each with:\n"
                '- "name": group name (e.g., "GAN-based approaches")\n'
                '- "paper_indices": list of paper numbers [1,3,5]\n'
                '- "description": 1-sentence description of this group'
            )},
        ]
        result = await llm_chat_json(messages, config=self.config)
        if isinstance(result, list):
            return result
        return [{"name": "All Papers", "paper_indices": list(range(1, len(papers) + 1)), "description": topic}]

    async def _stage4_analyze_group(
        self, topic: str, group: dict[str, Any], papers: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Analyze a single group of papers."""
        indices = group.get("paper_indices", [])
        group_papers = [papers[i - 1] for i in indices if 0 < i <= len(papers)]
        group_block = _paper_summary_block(group_papers)

        messages = [
            {"role": "system", "content": "You are a research analyst. Write in academic style."},
            {"role": "user", "content": (
                f"Topic: {topic}\n"
                f"Group: {group.get('name', 'Papers')}\n\n"
                f"Papers in this group:\n{group_block}\n\n"
                "Provide a detailed analysis:\n"
                "1. Key methods used across these papers\n"
                "2. Main arguments and findings\n"
                "3. How these papers compare to each other\n"
                "4. Strengths and limitations of this approach\n\n"
                "Use [N] to cite specific papers. Write 2-3 paragraphs."
            )},
        ]
        analysis_text = await llm_chat(messages, config=self.config)
        return {
            "group_name": group.get("name", "Papers"),
            "description": group.get("description", ""),
            "paper_count": len(group_papers),
            "analysis": analysis_text,
        }

    async def _stage5_synthesize(
        self, topic: str, group_analyses: list[dict[str, Any]]
    ) -> str:
        """Synthesize findings across all groups."""
        analyses_text = ""
        for ga in group_analyses:
            analyses_text += f"\n### {ga['group_name']}\n{ga['analysis']}\n"

        messages = [
            {"role": "system", "content": "You are a research synthesizer. Write in academic style."},
            {"role": "user", "content": (
                f"Topic: {topic}\n\n"
                f"Group analyses:\n{analyses_text}\n\n"
                "Synthesize across all groups:\n"
                "1. Points of agreement across approaches\n"
                "2. Contradictions or debates\n"
                "3. Temporal trends (which approaches are newer/older)\n"
                "4. Key research gaps and open questions\n\n"
                "Write 3-4 paragraphs."
            )},
        ]
        return await llm_chat(messages, config=self.config)

    async def _stage6_assemble(
        self,
        topic: str,
        papers: list[dict[str, Any]],
        group_analyses: list[dict[str, Any]],
        synthesis: str,
    ) -> str:
        """Assemble the final review document."""
        # Build reference list
        references: list[str] = []
        for i, p in enumerate(papers, 1):
            authors = p.get("authors_json", "[]")
            if isinstance(authors, str):
                authors = json.loads(authors)
            first_author = authors[0] if authors else "Unknown"
            et_al = " et al." if len(authors) > 1 else ""
            ref = f"{first_author}{et_al}, \"{p.get('title', 'Untitled')}\", {p.get('venue', '')}, {p.get('year', '')}."
            if p.get("doi"):
                ref += f" DOI: {p['doi']}"
            references.append(ref)

        # Build review sections
        sections: list[str] = []
        sections.append(f"# Literature Review: {topic}\n")
        sections.append(f"*Based on {len(papers)} papers from the knowledge base.*\n")

        # Introduction
        sections.append("## 1. Introduction\n")
        intro_msgs = [
            {"role": "system", "content": "Write a concise academic introduction paragraph."},
            {"role": "user", "content": (
                f"Write a 1-2 paragraph introduction for a literature review on '{topic}'. "
                f"Mention that it covers {len(papers)} papers across {len(group_analyses)} themes."
            )},
        ]
        intro = await llm_chat(intro_msgs, config=self.config)
        sections.append(intro + "\n")

        # Methodology Taxonomy
        sections.append("## 2. Methodology Taxonomy\n")
        for ga in group_analyses:
            sections.append(f"- **{ga['group_name']}** ({ga['paper_count']} papers): {ga['description']}")
        sections.append("")

        # Detailed Analysis
        sections.append("## 3. Detailed Analysis\n")
        for ga in group_analyses:
            sections.append(f"### 3.{group_analyses.index(ga)+1}. {ga['group_name']}\n")
            sections.append(ga["analysis"])
            sections.append("")

        # Cross-cutting Discussion
        sections.append("## 4. Discussion\n")
        sections.append(synthesis + "\n")

        # Research Gaps
        sections.append("## 5. Research Gaps and Future Directions\n")
        gaps_msgs = [
            {"role": "system", "content": "You are a research gap analyst."},
            {"role": "user", "content": (
                f"Based on this review of '{topic}':\n\n"
                f"Synthesis:\n{synthesis[:1000]}\n\n"
                "Identify 3-5 specific research gaps and suggest future research directions. "
                "Be concrete and cite which aspects are missing from current work."
            )},
        ]
        gaps = await llm_chat(gaps_msgs, config=self.config)
        sections.append(gaps + "\n")

        # References
        sections.append("## References\n")
        for i, ref in enumerate(references, 1):
            sections.append(f"[{i}] {ref}")
        sections.append("")

        return "\n".join(sections)
