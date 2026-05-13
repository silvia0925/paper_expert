"""Tests for Phase 3: review models, database CRUD, LLM utility, and engine logic."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from paper_expert.core.database import Database
from paper_expert.models.review import (
    DirectionReport,
    DomainKnowledgeEntry,
    DomainReport,
    NoveltyLevel,
    ResearchSuggestion,
    ReviewDocument,
    ReviewSection,
    TrendEntry,
)


# ── Model Tests ──────────────────────────────────────────


class TestReviewModels:
    def test_review_document_full_text(self) -> None:
        doc = ReviewDocument(
            topic="Neural OPC",
            sections=[
                ReviewSection(heading="Introduction", content="This is the intro."),
                ReviewSection(heading="Methods", content="Various methods used."),
            ],
            references=["Paper A", "Paper B"],
            paper_count=10,
        )
        text = doc.full_text
        assert "# Literature Review: Neural OPC" in text
        assert "## Introduction" in text
        assert "## Methods" in text
        assert "[1] Paper A" in text
        assert "[2] Paper B" in text

    def test_review_document_empty(self) -> None:
        doc = ReviewDocument(topic="empty")
        assert "empty" in doc.full_text

    def test_research_suggestion(self) -> None:
        s = ResearchSuggestion(
            title="KAN for ILT",
            description="Apply KAN to inverse lithography",
            evidence=["Paper X", "Paper Y"],
            novelty=NoveltyLevel.UNEXPLORED,
            reasoning="KAN excels at PDE solving",
        )
        assert s.novelty == NoveltyLevel.UNEXPLORED
        assert len(s.evidence) == 2

    def test_direction_report_full_text(self) -> None:
        report = DirectionReport(
            topic="AI Lithography",
            suggestions=[
                ResearchSuggestion(title="KAN + ILT", description="Explore KAN", novelty=NoveltyLevel.UNEXPLORED),
            ],
            trends=[
                TrendEntry(method_or_topic="GAN", direction="rising", paper_count=5, year_range="2020-2024", description="Gaining traction"),
            ],
            matrix_gaps=["KAN + OPC", "Diffusion + ILT"],
            paper_count_analyzed=20,
        )
        text = report.full_text
        assert "KAN + ILT" in text
        assert "[UNEXPLORED]" in text
        assert "GAN" in text
        assert "KAN + OPC" in text

    def test_domain_knowledge_entry(self) -> None:
        entry = DomainKnowledgeEntry(
            paper_id=1,
            paper_title="Test Paper",
            concepts=["OPC", "mask"],
            methods=["CNN", "GAN"],
            findings=["Improved accuracy"],
            limitations=["Slow inference"],
            relations=["Extends Paper X"],
        )
        assert len(entry.concepts) == 2
        assert entry.paper_id == 1

    def test_domain_report(self) -> None:
        report = DomainReport(topic="ILT", report_text="# Report\nContent here.", paper_count=5)
        assert report.full_text.startswith("# Report")

    def test_domain_report_empty(self) -> None:
        report = DomainReport(topic="ILT")
        assert "No report generated" in report.full_text


# ── Database CRUD Tests ──────────────────────────────────


@pytest.fixture
def db(tmp_path: Path) -> Database:
    return Database(tmp_path / "test.db")


class TestReviewCRUD:
    def test_save_and_get_review(self, db: Database) -> None:
        rid = db.save_review("neural OPC", "Review text here", paper_count=10)
        assert rid > 0

        result = db.get_review("neural OPC")
        assert result is not None
        assert result["review_text"] == "Review text here"
        assert result["paper_count"] == 10

    def test_get_review_with_scope(self, db: Database) -> None:
        db.save_review("OPC", "scoped review", scope="year:2024")
        db.save_review("OPC", "unscoped review")

        scoped = db.get_review("OPC", scope="year:2024")
        assert scoped is not None
        assert scoped["review_text"] == "scoped review"

        unscoped = db.get_review("OPC")
        assert unscoped is not None
        assert unscoped["review_text"] == "unscoped review"

    def test_get_nonexistent_review(self, db: Database) -> None:
        assert db.get_review("nonexistent") is None

    def test_list_reviews(self, db: Database) -> None:
        db.save_review("topic A", "text A")
        db.save_review("topic B", "text B")
        reviews = db.list_reviews()
        assert len(reviews) == 2


class TestDomainKnowledgeCRUD:
    def test_save_and_get(self, db: Database) -> None:
        paper_id = db.add_paper(title="Test Paper")
        db.save_domain_knowledge(
            topic="ILT", paper_id=paper_id,
            concepts=["OPC", "mask"], methods=["CNN"],
            findings=["Better accuracy"], limitations=["Slow"],
            relations=["Extends X"],
        )

        entries = db.get_domain_knowledge("ILT")
        assert len(entries) == 1
        assert entries[0]["concepts"] == ["OPC", "mask"]
        assert entries[0]["methods"] == ["CNN"]

    def test_get_digested_paper_ids(self, db: Database) -> None:
        p1 = db.add_paper(title="Paper 1")
        p2 = db.add_paper(title="Paper 2")
        db.save_domain_knowledge("ILT", p1, ["c"], ["m"], ["f"], ["l"], ["r"])

        digested = db.get_digested_paper_ids("ILT")
        assert p1 in digested
        assert p2 not in digested

    def test_incremental_update(self, db: Database) -> None:
        p1 = db.add_paper(title="Paper 1")
        db.save_domain_knowledge("ILT", p1, ["c1"], ["m1"], ["f1"], [], [])

        # Update same paper
        db.save_domain_knowledge("ILT", p1, ["c2"], ["m2"], ["f2"], [], [])
        entries = db.get_domain_knowledge("ILT")
        assert len(entries) == 1  # Upserted, not duplicated
        assert entries[0]["concepts"] == ["c2"]


class TestDomainReportCRUD:
    def test_save_and_get(self, db: Database) -> None:
        db.save_domain_report("ILT", "Report text", paper_count=15, model_used="gpt-5.2")
        result = db.get_domain_report("ILT")
        assert result is not None
        assert result["report_text"] == "Report text"
        assert result["paper_count"] == 15

    def test_overwrite_report(self, db: Database) -> None:
        db.save_domain_report("ILT", "V1", paper_count=10)
        db.save_domain_report("ILT", "V2", paper_count=20)
        result = db.get_domain_report("ILT")
        assert result["report_text"] == "V2"
        assert result["paper_count"] == 20

    def test_get_nonexistent(self, db: Database) -> None:
        assert db.get_domain_report("nope") is None


class TestSchemaV3Migration:
    def test_tables_exist(self, db: Database) -> None:
        with db.connection() as conn:
            for table in ("reviews", "domain_knowledge", "domain_reports"):
                row = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                    (table,),
                ).fetchone()
                assert row is not None, f"Table {table} missing"


# ── Direction Advisor Logic Tests ──────────────────────────


class TestTrendAnalysis:
    def test_trend_entry_model(self) -> None:
        t = TrendEntry(
            method_or_topic="GAN",
            direction="rising",
            paper_count=10,
            year_range="2020-2024",
            description="Increasing adoption",
        )
        assert t.direction == "rising"
        assert t.paper_count == 10
