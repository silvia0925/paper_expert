"""Unit tests for Database CRUD operations."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from paper_expert.core.database import Database


@pytest.fixture
def db(tmp_path: Path) -> Database:
    return Database(tmp_path / "test.db")


class TestPaperCRUD:
    def test_add_and_get_paper(self, db: Database) -> None:
        paper_id = db.add_paper(
            title="Test Paper",
            doi="10.1234/test",
            authors=["Alice", "Bob"],
            year=2024,
            venue="ICML",
            abstract="A test abstract.",
            source="semantic_scholar",
            state="full-text",
        )
        assert paper_id > 0

        paper = db.get_paper(paper_id)
        assert paper is not None
        assert paper["title"] == "Test Paper"
        assert paper["doi"] == "10.1234/test"
        assert json.loads(paper["authors_json"]) == ["Alice", "Bob"]
        assert paper["year"] == 2024

    def test_get_paper_by_doi(self, db: Database) -> None:
        db.add_paper(title="Paper A", doi="10.1234/a")
        paper = db.get_paper_by_doi("10.1234/a")
        assert paper is not None
        assert paper["title"] == "Paper A"

    def test_update_paper(self, db: Database) -> None:
        paper_id = db.add_paper(title="Old Title", state="pending")
        db.update_paper(paper_id, title="New Title", state="full-text")
        paper = db.get_paper(paper_id)
        assert paper["title"] == "New Title"
        assert paper["state"] == "full-text"

    def test_delete_paper(self, db: Database) -> None:
        paper_id = db.add_paper(title="To Delete")
        db.delete_paper(paper_id)
        assert db.get_paper(paper_id) is None

    def test_list_papers_with_filters(self, db: Database) -> None:
        db.add_paper(title="AI Paper", year=2024, state="full-text")
        db.add_paper(title="Litho Paper", year=2023, state="metadata-only")
        db.add_paper(title="Another AI", year=2024, state="full-text")

        all_papers = db.list_papers()
        assert len(all_papers) == 3

        by_year = db.list_papers(year=2024)
        assert len(by_year) == 2

        by_state = db.list_papers(state="metadata-only")
        assert len(by_state) == 1

    def test_paper_exists(self, db: Database) -> None:
        db.add_paper(title="Existing", doi="10.1234/exists")
        assert db.paper_exists(doi="10.1234/exists") is True
        assert db.paper_exists(doi="10.1234/nope") is False
        assert db.paper_exists(title="Existing") is True

    def test_count_papers(self, db: Database) -> None:
        db.add_paper(title="A", state="full-text")
        db.add_paper(title="B", state="metadata-only")
        assert db.count_papers() == 2
        assert db.count_papers(state="full-text") == 1


class TestTagCRUD:
    def test_add_and_get_tags(self, db: Database) -> None:
        paper_id = db.add_paper(title="Tagged Paper")
        db.add_tag(paper_id, "L0", "AI")
        db.add_tag(paper_id, "L1", "GAN", confidence=0.9)
        db.add_tag(paper_id, "L2", "important")

        tags = db.get_tags(paper_id)
        assert len(tags) == 3

        l0_tags = db.get_tags(paper_id, level="L0")
        assert len(l0_tags) == 1
        assert l0_tags[0]["tag"] == "AI"

    def test_remove_tag(self, db: Database) -> None:
        paper_id = db.add_paper(title="Paper")
        db.add_tag(paper_id, "L2", "to-read")
        db.remove_tag(paper_id, "to-read")
        assert len(db.get_tags(paper_id)) == 0

    def test_duplicate_tag_ignored(self, db: Database) -> None:
        paper_id = db.add_paper(title="Paper")
        db.add_tag(paper_id, "L0", "AI")
        db.add_tag(paper_id, "L0", "AI")  # should not error
        assert len(db.get_tags(paper_id, level="L0")) == 1

    def test_untagged_paper_ids(self, db: Database) -> None:
        p1 = db.add_paper(title="Tagged")
        p2 = db.add_paper(title="Untagged")
        db.add_tag(p1, "L1", "GAN")
        untagged = db.get_untagged_paper_ids(level="L1")
        assert p2 in untagged
        assert p1 not in untagged


class TestCitationCRUD:
    def test_add_and_get_citations(self, db: Database) -> None:
        p1 = db.add_paper(title="Paper A")
        p2 = db.add_paper(title="Paper B")
        p3 = db.add_paper(title="Paper C")
        db.add_citation(p1, p2)  # A cites B
        db.add_citation(p3, p1)  # C cites A

        refs = db.get_references(p1)  # A cites -> B
        assert len(refs) == 1
        assert refs[0]["title"] == "Paper B"

        cits = db.get_citations(p1)  # cited by -> C
        assert len(cits) == 1
        assert cits[0]["title"] == "Paper C"

    def test_duplicate_citation_ignored(self, db: Database) -> None:
        p1 = db.add_paper(title="A")
        p2 = db.add_paper(title="B")
        db.add_citation(p1, p2)
        db.add_citation(p1, p2)  # should not error
        assert db.get_reference_count(p1) == 1


class TestVocabulary:
    def test_add_and_normalize(self, db: Database) -> None:
        db.add_vocabulary("GAN", ["Generative Adversarial Network", "GANs"])

        assert db.normalize_tag("GAN") == "GAN"
        assert db.normalize_tag("Generative Adversarial Network") == "GAN"
        assert db.normalize_tag("GANs") == "GAN"
        assert db.normalize_tag("CNN") is None

    def test_remove_vocabulary(self, db: Database) -> None:
        db.add_vocabulary("OPC", ["Optical Proximity Correction"])
        db.remove_vocabulary("OPC")
        assert db.normalize_tag("OPC") is None


class TestStatistics:
    def test_get_stats(self, db: Database) -> None:
        db.add_paper(title="A", year=2024, state="full-text")
        db.add_paper(title="B", year=2024, state="metadata-only")
        p = db.add_paper(title="C", year=2023, state="full-text")
        db.add_tag(p, "L0", "AI")

        stats = db.get_stats()
        assert stats["total"] == 3
        assert stats["by_state"]["full-text"] == 2
        assert stats["by_year"][2024] == 2
        assert stats["by_category"]["AI"] == 1
