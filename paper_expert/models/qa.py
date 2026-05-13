"""Pydantic models for QA engine responses."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class ConfidenceLevel(str, Enum):
    """Confidence level of a QA answer."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class QASource(BaseModel):
    """A single source passage used to generate an answer."""

    paper_id: int | None = None
    paper_title: str = ""
    year: int | None = None
    passage: str = ""
    relevance_score: float = 0.0


class QAAnswer(BaseModel):
    """Result of a question-answering query."""

    answer: str = ""
    question: str = ""
    sources: list[QASource] = Field(default_factory=list)
    cost: float = 0.0
    confidence: ConfidenceLevel = ConfidenceLevel.LOW
    is_sufficient: bool = False
    error: str | None = None

    @property
    def source_count(self) -> int:
        return len(self.sources)

    def format_sources(self) -> str:
        """Format sources for display."""
        if not self.sources:
            return "No sources."
        lines: list[str] = []
        for i, s in enumerate(self.sources, 1):
            header = f"[{i}] {s.paper_title}"
            if s.year:
                header += f" ({s.year})"
            if s.paper_id:
                header += f"  [ID: {s.paper_id}]"
            lines.append(header)
            if s.passage:
                # Truncate long passages for display
                excerpt = s.passage[:200] + "..." if len(s.passage) > 200 else s.passage
                lines.append(f"    {excerpt}")
            lines.append("")
        return "\n".join(lines)
