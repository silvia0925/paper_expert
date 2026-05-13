"""Tests for QA models, confidence assessment, scope parsing, and database summaries."""

from __future__ import annotations

from pathlib import Path

import pytest

from paper_expert.core.database import Database
from paper_expert.core.qa_engine import assess_confidence, parse_scope
from paper_expert.models.qa import ConfidenceLevel, QAAnswer, QASource


# ── Model Tests ──────────────────────────────────────────


class TestQAModels:
    def test_qa_answer_defaults(self) -> None:
        a = QAAnswer(answer="test", question="q")
        assert a.confidence == ConfidenceLevel.LOW
        assert a.is_sufficient is False
        assert a.source_count == 0

    def test_qa_answer_with_sources(self) -> None:
        sources = [
            QASource(paper_id=1, paper_title="Paper A", passage="text", relevance_score=0.8),
            QASource(paper_id=2, paper_title="Paper B", passage="more", relevance_score=0.6),
        ]
        a = QAAnswer(
            answer="answer",
            question="q",
            sources=sources,
            confidence=ConfidenceLevel.HIGH,
            is_sufficient=True,
        )
        assert a.source_count == 2
        assert "Paper A" in a.format_sources()
        assert "Paper B" in a.format_sources()

    def test_qa_answer_error(self) -> None:
        a = QAAnswer(question="q", error="something broke")
        assert a.error == "something broke"
        assert a.answer == ""

    def test_format_sources_empty(self) -> None:
        a = QAAnswer(question="q")
        assert a.format_sources() == "No sources."


# ── Confidence Assessment ──────────────────────────────────


class TestConfidenceAssessment:
    def test_no_contexts(self) -> None:
        level, sufficient = assess_confidence([])
        assert level == ConfidenceLevel.LOW
        assert sufficient is False

    def test_one_context_insufficient(self) -> None:
        contexts = [{"score": 0.9}]
        level, sufficient = assess_confidence(contexts)
        assert level == ConfidenceLevel.LOW
        assert sufficient is False

    def test_high_confidence(self) -> None:
        contexts = [{"score": 0.8}, {"score": 0.75}, {"score": 0.9}]
        level, sufficient = assess_confidence(contexts)
        assert level == ConfidenceLevel.HIGH
        assert sufficient is True

    def test_medium_confidence(self) -> None:
        contexts = [{"score": 0.5}, {"score": 0.45}]
        level, sufficient = assess_confidence(contexts)
        assert level == ConfidenceLevel.MEDIUM
        assert sufficient is True

    def test_low_confidence_with_contexts(self) -> None:
        contexts = [{"score": 0.1}, {"score": 0.2}]
        level, sufficient = assess_confidence(contexts)
        assert level == ConfidenceLevel.LOW
        assert sufficient is False


# ── Scope Parsing ──────────────────────────────────────────


class TestScopeParsing:
    def test_tag_scope(self) -> None:
        result = parse_scope("tag:OPC")
        assert result == {"tag": "OPC"}

    def test_year_scope(self) -> None:
        result = parse_scope("year:2024-2025")
        assert result == {"year": "2024-2025"}

    def test_combined_scope(self) -> None:
        result = parse_scope("tag:GAN, year:2024")
        assert result == {"tag": "GAN", "year": "2024"}

    def test_empty_scope(self) -> None:
        result = parse_scope("")
        assert result == {}


# ── Database Summary CRUD ──────────────────────────────────


@pytest.fixture
def db(tmp_path: Path) -> Database:
    return Database(tmp_path / "test.db")


class TestSummaryCRUD:
    def test_save_and_get_summary(self, db: Database) -> None:
        paper_id = db.add_paper(title="Test Paper")
        db.save_summary(paper_id, "This is a summary.", "gpt-4o")

        result = db.get_summary(paper_id)
        assert result is not None
        assert result["summary_text"] == "This is a summary."
        assert result["model_used"] == "gpt-4o"
        assert result["generated_at"] is not None

    def test_get_nonexistent_summary(self, db: Database) -> None:
        assert db.get_summary(999) is None

    def test_overwrite_summary(self, db: Database) -> None:
        paper_id = db.add_paper(title="Paper")
        db.save_summary(paper_id, "First version", "gpt-4o")
        db.save_summary(paper_id, "Updated version", "gpt-4o-mini")

        result = db.get_summary(paper_id)
        assert result is not None
        assert result["summary_text"] == "Updated version"

    def test_summary_deleted_with_paper(self, db: Database) -> None:
        paper_id = db.add_paper(title="To Delete")
        db.save_summary(paper_id, "Summary", "model")
        db.delete_paper(paper_id)
        assert db.get_summary(paper_id) is None

    def test_schema_migration_v2(self, db: Database) -> None:
        """Verify summaries table exists after migration."""
        with db.connection() as conn:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='summaries'"
            ).fetchone()
            assert row is not None
