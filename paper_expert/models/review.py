"""Pydantic models for literature review, research direction, and domain knowledge."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class NoveltyLevel(str, Enum):
    """How novel/unexplored a research direction is."""

    UNEXPLORED = "unexplored"
    EMERGING = "emerging"
    ACTIVE = "active"


# ── Literature Review ──────────────────────────────────


class ReviewSection(BaseModel):
    """A section of a literature review."""

    heading: str = ""
    content: str = ""


class ReviewDocument(BaseModel):
    """A complete literature review."""

    topic: str = ""
    sections: list[ReviewSection] = Field(default_factory=list)
    references: list[str] = Field(default_factory=list)  # paper titles or IDs
    paper_count: int = 0
    scope: str | None = None

    @property
    def full_text(self) -> str:
        """Render the review as a single Markdown string."""
        parts: list[str] = [f"# Literature Review: {self.topic}\n"]
        for section in self.sections:
            parts.append(f"## {section.heading}\n")
            parts.append(section.content)
            parts.append("")
        if self.references:
            parts.append("## References\n")
            for i, ref in enumerate(self.references, 1):
                parts.append(f"[{i}] {ref}")
            parts.append("")
        return "\n".join(parts)


# ── Research Direction ──────────────────────────────────


class ResearchSuggestion(BaseModel):
    """A suggested research direction."""

    title: str = ""
    description: str = ""
    evidence: list[str] = Field(default_factory=list)  # paper titles/IDs supporting this
    novelty: NoveltyLevel = NoveltyLevel.EMERGING
    reasoning: str = ""


class TrendEntry(BaseModel):
    """A detected research trend."""

    method_or_topic: str = ""
    direction: str = ""  # "rising", "declining", "stable"
    paper_count: int = 0
    year_range: str = ""
    description: str = ""


class DirectionReport(BaseModel):
    """Complete research direction analysis."""

    topic: str = ""
    suggestions: list[ResearchSuggestion] = Field(default_factory=list)
    trends: list[TrendEntry] = Field(default_factory=list)
    matrix_gaps: list[str] = Field(default_factory=list)  # "method X + problem Y"
    paper_count_analyzed: int = 0

    @property
    def full_text(self) -> str:
        parts: list[str] = [f"# Research Direction Analysis: {self.topic}\n"]
        parts.append(f"Based on {self.paper_count_analyzed} papers.\n")

        if self.suggestions:
            parts.append("## Suggested Directions\n")
            for i, s in enumerate(self.suggestions, 1):
                novelty_label = f"[{s.novelty.value.upper()}]"
                parts.append(f"### {i}. {s.title} {novelty_label}\n")
                parts.append(s.description)
                if s.reasoning:
                    parts.append(f"\n**Reasoning:** {s.reasoning}")
                if s.evidence:
                    parts.append(f"\n**Evidence:** {', '.join(s.evidence)}")
                parts.append("")

        if self.trends:
            parts.append("## Trends\n")
            for t in self.trends:
                arrow = {"rising": "^", "declining": "v", "stable": "-"}.get(t.direction, "?")
                parts.append(f"- [{arrow}] **{t.method_or_topic}** ({t.year_range}, {t.paper_count} papers): {t.description}")
            parts.append("")

        if self.matrix_gaps:
            parts.append("## Unexplored Combinations\n")
            for gap in self.matrix_gaps:
                parts.append(f"- {gap}")
            parts.append("")

        return "\n".join(parts)


# ── Domain Knowledge ──────────────────────────────────


class DomainKnowledgeEntry(BaseModel):
    """Structured knowledge extracted from a single paper."""

    paper_id: int
    paper_title: str = ""
    concepts: list[str] = Field(default_factory=list)
    methods: list[str] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    relations: list[str] = Field(default_factory=list)  # "extends Paper X", "contradicts Y"


class DomainReport(BaseModel):
    """Comprehensive domain knowledge report."""

    topic: str = ""
    report_text: str = ""
    paper_count: int = 0

    @property
    def full_text(self) -> str:
        if self.report_text:
            return self.report_text
        return f"# Domain Knowledge: {self.topic}\n\nNo report generated yet."
