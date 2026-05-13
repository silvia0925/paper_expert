"""Domain Expert Engine �?systematic knowledge building from paper reading.

Digests papers individually into structured knowledge, then synthesizes
into a comprehensive domain report. Supports incremental updates.
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


class DomainExpert:
    """Builds domain expertise by systematically reading and digesting papers."""

    def __init__(self, db: Database, config: PaperExpertConfig) -> None:
        self.db = db
        self.config = config

    async def build(
        self,
        topic: str,
        update: bool = False,
        on_progress: ProgressCallback | None = None,
    ) -> str:
        """Build or update domain expertise for a topic.

        Returns the domain report text (with change summary when update=True).
        """
        def _progress(msg: str) -> None:
            if on_progress:
                on_progress(msg)

        # Check existing report
        if not update:
            existing = self.db.get_domain_report(topic)
            if existing:
                _progress("Returning existing domain report")
                return existing["report_text"]

        # Capture pre-update state for delta
        old_report = self.db.get_domain_report(topic) if update else None
        old_paper_count = old_report["paper_count"] if old_report else 0
        old_generated_at = old_report.get("generated_at", "unknown") if old_report else None
        already_digested = self.db.get_digested_paper_ids(topic)

        # Get relevant papers
        papers = self._get_topic_papers(topic)
        if not papers:
            return f"No papers found for topic '{topic}'. Add papers first."

        # Determine which papers need digestion
        to_digest = [p for p in papers if p["id"] not in already_digested]

        _progress(f"Found {len(papers)} papers, {len(to_digest)} new to digest")

        # Digest new papers
        for i, paper in enumerate(to_digest, 1):
            _progress(f"Digesting [{i}/{len(to_digest)}]: {paper['title'][:50]}...")
            await self._digest_paper(topic, paper)

        # Generate report from all digested knowledge
        _progress("Generating domain report...")
        knowledge = self.db.get_domain_knowledge(topic)
        report_text = await self._generate_report(topic, knowledge, papers)

        # Build change summary for updates
        if update and old_report is not None and to_digest:
            delta = _build_delta_summary(
                topic=topic,
                new_papers=to_digest,
                old_paper_count=old_paper_count,
                new_paper_count=len(papers),
                old_generated_at=old_generated_at or "unknown",
            )
            report_text = delta + "\n---\n\n" + report_text

        # Save report
        model = self.config.llm.cloud_model
        self.db.save_domain_report(topic, report_text, paper_count=len(papers), model_used=model)
        _progress(f"Domain report complete ({len(papers)} papers)")

        return report_text

    async def ask_expert(
        self,
        topic: str,
        question: str,
    ) -> str:
        """Answer a question using domain knowledge + paper QA.

        Leverages structured domain knowledge for deeper, contextualized answers.
        """
        # Load domain knowledge
        knowledge = self.db.get_domain_knowledge(topic)
        report = self.db.get_domain_report(topic)

        if not knowledge and not report:
            return (
                f"No domain expertise built for '{topic}'. "
                f"Run `paper_expert expert \"{topic}\"` first to build knowledge."
            )

        # Build context from domain knowledge
        context_parts: list[str] = []
        if report:
            # Use report summary (first 2000 chars)
            context_parts.append(f"Domain Report Summary:\n{report['report_text'][:2000]}")

        # Add relevant knowledge entries
        all_concepts = set()
        all_methods = set()
        for k in knowledge:
            all_concepts.update(k.get("concepts", []))
            all_methods.update(k.get("methods", []))

        context_parts.append(f"\nKey Concepts: {', '.join(sorted(all_concepts)[:20])}")
        context_parts.append(f"Key Methods: {', '.join(sorted(all_methods)[:20])}")

        # Find entries most relevant to the question
        relevant_entries: list[str] = []
        q_lower = question.lower()
        for k in knowledge:
            combined = " ".join(
                k.get("concepts", []) + k.get("methods", []) +
                k.get("findings", []) + k.get("limitations", [])
            ).lower()
            if any(word in combined for word in q_lower.split()):
                findings = k.get("findings", [])[:3]
                limitations = k.get("limitations", [])[:2]
                relevant_entries.append(
                    f"Paper: {k.get('paper_title', '?')}\n"
                    f"  Findings: {'; '.join(findings)}\n"
                    f"  Limitations: {'; '.join(limitations)}"
                )

        if relevant_entries:
            context_parts.append("\nRelevant Paper Findings:\n" + "\n".join(relevant_entries[:10]))

        context = "\n".join(context_parts)

        messages = [
            {"role": "system", "content": (
                "You are a domain expert. Answer the question using the provided domain knowledge. "
                "Include historical context, compare methods where relevant, and provide forward-looking analysis. "
                "Cite specific papers when possible."
            )},
            {"role": "user", "content": (
                f"Domain: {topic}\n\n"
                f"Knowledge Context:\n{context}\n\n"
                f"Question: {question}"
            )},
        ]
        return await llm_chat(messages, config=self.config)

    # ── Internal methods ──────────────────────────────────

    def _get_topic_papers(self, topic: str) -> list[dict[str, Any]]:
        """Get papers related to a topic."""
        with self.db.connection() as conn:
            pattern = f"%{topic}%"
            rows = conn.execute(
                "SELECT * FROM papers WHERE title LIKE ? OR abstract LIKE ? ORDER BY citation_count DESC LIMIT 50",
                (pattern, pattern),
            ).fetchall()
            return [dict(r) for r in rows]

    async def _digest_paper(self, topic: str, paper: dict[str, Any]) -> None:
        """Extract structured knowledge from a single paper."""
        authors = paper.get("authors_json", "[]")
        if isinstance(authors, str):
            authors = json.loads(authors)
        first_author = authors[0] if authors else "Unknown"

        abstract = paper.get("abstract") or "No abstract available."

        messages = [
            {"role": "system", "content": "You are a research paper analyst. Output valid JSON only."},
            {"role": "user", "content": (
                f"Paper: {paper.get('title', 'Untitled')} ({first_author} et al., {paper.get('year', '?')})\n"
                f"Abstract: {abstract}\n\n"
                "Extract structured knowledge:\n"
                '- "concepts": list of key concepts/terms introduced or used\n'
                '- "methods": list of methods/techniques/algorithms used\n'
                '- "findings": list of key findings/contributions (2-4 items)\n'
                '- "limitations": list of limitations mentioned or apparent\n'
                '- "relations": list of relationships to other work (e.g., "extends X", "improves on Y")\n\n'
                "Return as JSON object."
            )},
        ]
        result = await llm_chat_json(messages, config=self.config)

        self.db.save_domain_knowledge(
            topic=topic,
            paper_id=paper["id"],
            concepts=result.get("concepts", []),
            methods=result.get("methods", []),
            findings=result.get("findings", []),
            limitations=result.get("limitations", []),
            relations=result.get("relations", []),
        )

    async def _generate_report(
        self,
        topic: str,
        knowledge: list[dict[str, Any]],
        papers: list[dict[str, Any]],
    ) -> str:
        """Synthesize all digested knowledge into a domain report."""
        # Aggregate knowledge
        all_concepts: dict[str, int] = {}
        all_methods: dict[str, int] = {}
        all_findings: list[str] = []
        all_limitations: list[str] = []
        all_relations: list[str] = []

        for k in knowledge:
            for c in k.get("concepts", []):
                all_concepts[c] = all_concepts.get(c, 0) + 1
            for m in k.get("methods", []):
                all_methods[m] = all_methods.get(m, 0) + 1
            all_findings.extend(k.get("findings", [])[:2])
            all_limitations.extend(k.get("limitations", [])[:1])
            all_relations.extend(k.get("relations", []))

        # Sort by frequency
        top_concepts = sorted(all_concepts.items(), key=lambda x: -x[1])[:15]
        top_methods = sorted(all_methods.items(), key=lambda x: -x[1])[:10]

        knowledge_summary = (
            f"Papers analyzed: {len(papers)}\n"
            f"Top concepts: {', '.join(f'{c}({n})' for c, n in top_concepts)}\n"
            f"Top methods: {', '.join(f'{m}({n})' for m, n in top_methods)}\n"
            f"Key findings ({len(all_findings)} total): {'; '.join(all_findings[:10])}\n"
            f"Limitations noted: {'; '.join(all_limitations[:5])}\n"
            f"Relations: {'; '.join(all_relations[:10])}"
        )

        messages = [
            {"role": "system", "content": (
                "You are a domain expert writing a comprehensive knowledge report. "
                "Write in academic style with clear structure."
            )},
            {"role": "user", "content": (
                f"Domain: {topic}\n\n"
                f"Aggregated knowledge from {len(papers)} papers:\n{knowledge_summary}\n\n"
                "Generate a comprehensive domain knowledge report with these sections:\n"
                "1. **Concept Map**: Key concepts and their relationships\n"
                "2. **Method Evolution**: How approaches have developed over time\n"
                "3. **Key Debates**: Opposing viewpoints and unresolved questions\n"
                "4. **Landmark Papers**: Most influential works and their contributions\n"
                "5. **State of the Art**: What works best today, and its limitations\n\n"
                "Write 4-6 paragraphs total. Be specific, cite concepts and methods."
            )},
        ]
        report = await llm_chat(messages, config=self.config, max_tokens=6000)

        header = (
            f"# Domain Knowledge Report: {topic}\n\n"
            f"*Based on {len(papers)} papers, {len(knowledge)} analyzed.*\n\n"
        )
        return header + report


def _build_delta_summary(
    topic: str,
    new_papers: list[dict[str, Any]],
    old_paper_count: int,
    new_paper_count: int,
    old_generated_at: str,
) -> str:
    """Build a human-readable summary of what changed since last update."""
    paper_names = [p.get("title", f"Paper #{p['id']}")[:80] for p in new_papers]
    added = new_paper_count - old_paper_count

    lines = [
        f"## 📋 Update Summary (since {old_generated_at[:10]})",
        f"",
        f"- **{len(new_papers)} new paper(s)** digested:",
    ]
    for name in paper_names:
        lines.append(f"  - {name}")
    lines.append(f"- Library grew from {old_paper_count} → {new_paper_count} papers "
                  f"({added:+d})")
    lines.append(f"- Report regenerated with all accumulated knowledge\n")
    return "\n".join(lines) + "\n"
