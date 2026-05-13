"""SQLite database for paper metadata, tags, citations, and vocabulary.

This is the source of truth for all paper metadata. PaperQA2 Docs serialization
handles vector indices separately.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

_SCHEMA_VERSION = 4

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS papers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doi TEXT UNIQUE,
    title TEXT NOT NULL,
    authors_json TEXT NOT NULL DEFAULT '[]',
    year INTEGER,
    venue TEXT,
    abstract TEXT,
    source TEXT NOT NULL DEFAULT 'manual',
    state TEXT NOT NULL DEFAULT 'pending',
    arxiv_id TEXT,
    s2_paper_id TEXT,
    citation_count INTEGER DEFAULT 0,
    pdf_path TEXT,
    parsed_path TEXT,
    date_added TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    paper_id INTEGER NOT NULL,
    level TEXT NOT NULL CHECK (level IN ('L0', 'L1', 'L2')),
    tag TEXT NOT NULL,
    confidence REAL,
    suggested INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (paper_id) REFERENCES papers(id) ON DELETE CASCADE,
    UNIQUE (paper_id, level, tag)
);

CREATE TABLE IF NOT EXISTS citations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    citing_paper_id INTEGER NOT NULL,
    cited_paper_id INTEGER NOT NULL,
    FOREIGN KEY (citing_paper_id) REFERENCES papers(id) ON DELETE CASCADE,
    FOREIGN KEY (cited_paper_id) REFERENCES papers(id) ON DELETE CASCADE,
    UNIQUE (citing_paper_id, cited_paper_id)
);

CREATE TABLE IF NOT EXISTS vocabulary (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical TEXT NOT NULL UNIQUE,
    aliases_json TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    paper_id INTEGER NOT NULL UNIQUE,
    summary_text TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    model_used TEXT,
    FOREIGN KEY (paper_id) REFERENCES papers(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic TEXT NOT NULL,
    review_text TEXT NOT NULL,
    paper_count INTEGER DEFAULT 0,
    scope TEXT,
    generated_at TEXT NOT NULL,
    model_used TEXT
);

CREATE TABLE IF NOT EXISTS domain_knowledge (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic TEXT NOT NULL,
    paper_id INTEGER NOT NULL,
    concepts_json TEXT NOT NULL DEFAULT '[]',
    methods_json TEXT NOT NULL DEFAULT '[]',
    findings_json TEXT NOT NULL DEFAULT '[]',
    limitations_json TEXT NOT NULL DEFAULT '[]',
    relations_json TEXT NOT NULL DEFAULT '[]',
    digested_at TEXT NOT NULL,
    FOREIGN KEY (paper_id) REFERENCES papers(id) ON DELETE CASCADE,
    UNIQUE (topic, paper_id)
);

CREATE TABLE IF NOT EXISTS domain_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic TEXT NOT NULL UNIQUE,
    report_text TEXT NOT NULL,
    paper_count INTEGER DEFAULT 0,
    generated_at TEXT NOT NULL,
    model_used TEXT
);

CREATE TABLE IF NOT EXISTS watch_topics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    queries_json TEXT NOT NULL DEFAULT '[]',
    sources_json TEXT NOT NULL DEFAULT '[]',
    fetch_limit INTEGER DEFAULT 10,
    notify_channels_json TEXT NOT NULL DEFAULT '[]',
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    last_run_at TEXT
);

CREATE TABLE IF NOT EXISTS watch_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    watch_id INTEGER NOT NULL,
    run_at TEXT NOT NULL,
    papers_found INTEGER DEFAULT 0,
    papers_added INTEGER DEFAULT 0,
    notify_status TEXT DEFAULT 'none',
    error TEXT,
    FOREIGN KEY (watch_id) REFERENCES watch_topics(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_watch_topics_active ON watch_topics(is_active);
CREATE INDEX IF NOT EXISTS idx_watch_logs_watch ON watch_logs(watch_id);
CREATE INDEX IF NOT EXISTS idx_watch_logs_run ON watch_logs(run_at);

CREATE INDEX IF NOT EXISTS idx_reviews_topic ON reviews(topic);
CREATE INDEX IF NOT EXISTS idx_domain_knowledge_topic ON domain_knowledge(topic);
CREATE INDEX IF NOT EXISTS idx_domain_knowledge_paper ON domain_knowledge(paper_id);

CREATE INDEX IF NOT EXISTS idx_papers_doi ON papers(doi);
CREATE INDEX IF NOT EXISTS idx_papers_s2_paper_id ON papers(s2_paper_id);
CREATE INDEX IF NOT EXISTS idx_papers_arxiv_id ON papers(arxiv_id);
CREATE INDEX IF NOT EXISTS idx_papers_state ON papers(state);
CREATE INDEX IF NOT EXISTS idx_papers_year ON papers(year);
CREATE INDEX IF NOT EXISTS idx_tags_paper_id ON tags(paper_id);
CREATE INDEX IF NOT EXISTS idx_tags_tag ON tags(tag);
CREATE INDEX IF NOT EXISTS idx_citations_citing ON citations(citing_paper_id);
CREATE INDEX IF NOT EXISTS idx_citations_cited ON citations(cited_paper_id);
"""


class Database:
    """SQLite database manager for Paper Expert."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None
        self._init_db()

    def _init_db(self) -> None:
        """Initialize database schema if needed."""
        with self.connection() as conn:
            conn.executescript(_SCHEMA_SQL)
            # Check/set schema version
            row = conn.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO schema_version (version) VALUES (?)", (_SCHEMA_VERSION,)
                )
            elif row["version"] < _SCHEMA_VERSION:
                self._migrate(conn, row["version"])

    def _migrate(self, conn: sqlite3.Connection, from_version: int) -> None:
        """Run schema migrations."""
        if from_version < 2:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS summaries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    paper_id INTEGER NOT NULL UNIQUE,
                    summary_text TEXT NOT NULL,
                    generated_at TEXT NOT NULL,
                    model_used TEXT,
                    FOREIGN KEY (paper_id) REFERENCES papers(id) ON DELETE CASCADE
                )"""
            )
        if from_version < 3:
            # v3: reviews, domain_knowledge, domain_reports
            conn.execute(
                """CREATE TABLE IF NOT EXISTS reviews (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    topic TEXT NOT NULL,
                    review_text TEXT NOT NULL,
                    paper_count INTEGER DEFAULT 0,
                    scope TEXT,
                    generated_at TEXT NOT NULL,
                    model_used TEXT
                )"""
            )
            conn.execute(
                """CREATE TABLE IF NOT EXISTS domain_knowledge (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    topic TEXT NOT NULL,
                    paper_id INTEGER NOT NULL,
                    concepts_json TEXT NOT NULL DEFAULT '[]',
                    methods_json TEXT NOT NULL DEFAULT '[]',
                    findings_json TEXT NOT NULL DEFAULT '[]',
                    limitations_json TEXT NOT NULL DEFAULT '[]',
                    relations_json TEXT NOT NULL DEFAULT '[]',
                    digested_at TEXT NOT NULL,
                    FOREIGN KEY (paper_id) REFERENCES papers(id) ON DELETE CASCADE,
                    UNIQUE (topic, paper_id)
                )"""
            )
            conn.execute(
                """CREATE TABLE IF NOT EXISTS domain_reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    topic TEXT NOT NULL UNIQUE,
                    report_text TEXT NOT NULL,
                    paper_count INTEGER DEFAULT 0,
                    generated_at TEXT NOT NULL,
                    model_used TEXT
                )"""
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_reviews_topic ON reviews(topic)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_domain_knowledge_topic ON domain_knowledge(topic)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_domain_knowledge_paper ON domain_knowledge(paper_id)")
        if from_version < 4:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS watch_topics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    queries_json TEXT NOT NULL DEFAULT '[]',
                    sources_json TEXT NOT NULL DEFAULT '[]',
                    fetch_limit INTEGER DEFAULT 10,
                    notify_channels_json TEXT NOT NULL DEFAULT '[]',
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    last_run_at TEXT
                )"""
            )
            conn.execute(
                """CREATE TABLE IF NOT EXISTS watch_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    watch_id INTEGER NOT NULL,
                    run_at TEXT NOT NULL,
                    papers_found INTEGER DEFAULT 0,
                    papers_added INTEGER DEFAULT 0,
                    notify_status TEXT DEFAULT 'none',
                    error TEXT,
                    FOREIGN KEY (watch_id) REFERENCES watch_topics(id) ON DELETE CASCADE
                )"""
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_watch_topics_active ON watch_topics(is_active)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_watch_logs_watch ON watch_logs(watch_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_watch_logs_run ON watch_logs(run_at)"
            )
        conn.execute(
            "UPDATE schema_version SET version = ?", (_SCHEMA_VERSION,)
        )

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        """Context manager for database connections."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ── Paper CRUD ──────────────────────────────────────────────

    def add_paper(
        self,
        title: str,
        doi: str | None = None,
        authors: list[str] | None = None,
        year: int | None = None,
        venue: str | None = None,
        abstract: str | None = None,
        source: str = "manual",
        state: str = "pending",
        arxiv_id: str | None = None,
        s2_paper_id: str | None = None,
        citation_count: int = 0,
        pdf_path: str | None = None,
        parsed_path: str | None = None,
    ) -> int:
        """Add a paper to the database. Returns the paper ID."""
        now = datetime.now(timezone.utc).isoformat()
        authors_json = json.dumps(authors or [])
        with self.connection() as conn:
            cursor = conn.execute(
                """INSERT INTO papers
                   (doi, title, authors_json, year, venue, abstract, source, state,
                    arxiv_id, s2_paper_id, citation_count, pdf_path, parsed_path, date_added)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    doi, title, authors_json, year, venue, abstract, source, state,
                    arxiv_id, s2_paper_id, citation_count, pdf_path, parsed_path, now,
                ),
            )
            return cursor.lastrowid  # type: ignore[return-value]

    def get_paper(self, paper_id: int) -> dict[str, Any] | None:
        """Get a paper by ID."""
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM papers WHERE id = ?", (paper_id,)).fetchone()
            return dict(row) if row else None

    def get_paper_by_doi(self, doi: str) -> dict[str, Any] | None:
        """Get a paper by DOI."""
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM papers WHERE doi = ?", (doi,)).fetchone()
            return dict(row) if row else None

    def get_paper_by_s2_id(self, s2_paper_id: str) -> dict[str, Any] | None:
        """Get a paper by Semantic PaperExpert paper ID."""
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM papers WHERE s2_paper_id = ?", (s2_paper_id,)
            ).fetchone()
            return dict(row) if row else None

    def update_paper(self, paper_id: int, **kwargs: Any) -> None:
        """Update paper fields by ID."""
        if "authors" in kwargs:
            kwargs["authors_json"] = json.dumps(kwargs.pop("authors"))
        allowed = {
            "doi", "title", "authors_json", "year", "venue", "abstract", "source",
            "state", "arxiv_id", "s2_paper_id", "citation_count", "pdf_path", "parsed_path",
        }
        fields = {k: v for k, v in kwargs.items() if k in allowed}
        if not fields:
            return
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [paper_id]
        with self.connection() as conn:
            conn.execute(f"UPDATE papers SET {set_clause} WHERE id = ?", values)

    def delete_paper(self, paper_id: int) -> None:
        """Delete a paper and its associated tags/citations."""
        with self.connection() as conn:
            conn.execute("DELETE FROM papers WHERE id = ?", (paper_id,))

    def list_papers(
        self,
        state: str | None = None,
        year: int | None = None,
        tag: str | None = None,
        sort_by: str = "date_added",
        sort_desc: bool = True,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """List papers with optional filters."""
        query = "SELECT DISTINCT p.* FROM papers p"
        conditions: list[str] = []
        params: list[Any] = []

        if tag is not None:
            query += " JOIN tags t ON t.paper_id = p.id"
            conditions.append("t.tag = ?")
            params.append(tag)

        if state is not None:
            conditions.append("p.state = ?")
            params.append(state)

        if year is not None:
            conditions.append("p.year = ?")
            params.append(year)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        allowed_sort = {"date_added", "year", "citation_count", "title"}
        if sort_by not in allowed_sort:
            sort_by = "date_added"
        direction = "DESC" if sort_desc else "ASC"
        query += f" ORDER BY p.{sort_by} {direction} LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        with self.connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    def count_papers(self, state: str | None = None) -> int:
        """Count papers, optionally filtered by state."""
        if state:
            with self.connection() as conn:
                row = conn.execute(
                    "SELECT COUNT(*) as cnt FROM papers WHERE state = ?", (state,)
                ).fetchone()
        else:
            with self.connection() as conn:
                row = conn.execute("SELECT COUNT(*) as cnt FROM papers").fetchone()
        return row["cnt"] if row else 0

    def paper_exists(self, doi: str | None = None, title: str | None = None) -> bool:
        """Check if a paper already exists by DOI or exact title."""
        with self.connection() as conn:
            if doi:
                row = conn.execute(
                    "SELECT 1 FROM papers WHERE doi = ?", (doi,)
                ).fetchone()
                if row:
                    return True
            if title:
                row = conn.execute(
                    "SELECT 1 FROM papers WHERE title = ?", (title,)
                ).fetchone()
                if row:
                    return True
        return False

    # ── Tag CRUD ──────────────────────────────────────────────

    def add_tag(
        self,
        paper_id: int,
        level: str,
        tag: str,
        confidence: float | None = None,
        suggested: bool = False,
    ) -> None:
        """Add a tag to a paper. Ignores duplicates."""
        with self.connection() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO tags (paper_id, level, tag, confidence, suggested)
                   VALUES (?, ?, ?, ?, ?)""",
                (paper_id, level, tag, confidence, 1 if suggested else 0),
            )

    def remove_tag(self, paper_id: int, tag: str) -> None:
        """Remove a tag from a paper."""
        with self.connection() as conn:
            conn.execute(
                "DELETE FROM tags WHERE paper_id = ? AND tag = ?", (paper_id, tag)
            )

    def get_tags(self, paper_id: int, level: str | None = None) -> list[dict[str, Any]]:
        """Get tags for a paper, optionally filtered by level."""
        with self.connection() as conn:
            if level:
                rows = conn.execute(
                    "SELECT * FROM tags WHERE paper_id = ? AND level = ?", (paper_id, level)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM tags WHERE paper_id = ?", (paper_id,)
                ).fetchall()
            return [dict(r) for r in rows]

    def get_suggested_tag_counts(self) -> list[dict[str, Any]]:
        """Get suggested tags with their paper counts (for vocabulary promotion)."""
        with self.connection() as conn:
            rows = conn.execute(
                """SELECT tag, COUNT(*) as count FROM tags
                   WHERE suggested = 1 GROUP BY tag ORDER BY count DESC"""
            ).fetchall()
            return [dict(r) for r in rows]

    def get_untagged_paper_ids(self, level: str = "L1") -> list[int]:
        """Get IDs of papers that have no tags at the specified level."""
        with self.connection() as conn:
            rows = conn.execute(
                """SELECT p.id FROM papers p
                   WHERE NOT EXISTS (
                       SELECT 1 FROM tags t WHERE t.paper_id = p.id AND t.level = ?
                   )""",
                (level,),
            ).fetchall()
            return [r["id"] for r in rows]

    # ── Citation CRUD ──────────────────────────────────────────

    def add_citation(self, citing_paper_id: int, cited_paper_id: int) -> None:
        """Add a citation edge. Ignores duplicates."""
        with self.connection() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO citations (citing_paper_id, cited_paper_id)
                   VALUES (?, ?)""",
                (citing_paper_id, cited_paper_id),
            )

    def get_references(self, paper_id: int) -> list[dict[str, Any]]:
        """Get papers that this paper cites (outgoing)."""
        with self.connection() as conn:
            rows = conn.execute(
                """SELECT p.* FROM papers p
                   JOIN citations c ON c.cited_paper_id = p.id
                   WHERE c.citing_paper_id = ?""",
                (paper_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_citations(self, paper_id: int) -> list[dict[str, Any]]:
        """Get papers that cite this paper (incoming)."""
        with self.connection() as conn:
            rows = conn.execute(
                """SELECT p.* FROM papers p
                   JOIN citations c ON c.citing_paper_id = p.id
                   WHERE c.cited_paper_id = ?""",
                (paper_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_reference_count(self, paper_id: int) -> int:
        """Count papers this paper cites."""
        with self.connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM citations WHERE citing_paper_id = ?",
                (paper_id,),
            ).fetchone()
            return row["cnt"] if row else 0

    def get_citation_count(self, paper_id: int) -> int:
        """Count papers that cite this paper."""
        with self.connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM citations WHERE cited_paper_id = ?",
                (paper_id,),
            ).fetchone()
            return row["cnt"] if row else 0

    # ── Vocabulary CRUD ──────────────────────────────────────────

    def add_vocabulary(self, canonical: str, aliases: list[str] | None = None) -> None:
        """Add a controlled vocabulary entry."""
        aliases_json = json.dumps(aliases or [])
        with self.connection() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO vocabulary (canonical, aliases_json)
                   VALUES (?, ?)""",
                (canonical, aliases_json),
            )

    def get_vocabulary(self) -> list[dict[str, Any]]:
        """Get all vocabulary entries."""
        with self.connection() as conn:
            rows = conn.execute("SELECT * FROM vocabulary ORDER BY canonical").fetchall()
            return [dict(r) for r in rows]

    def normalize_tag(self, raw_tag: str) -> str | None:
        """Normalize a tag against the controlled vocabulary. Returns canonical or None."""
        raw_lower = raw_tag.lower().strip()
        with self.connection() as conn:
            rows = conn.execute("SELECT canonical, aliases_json FROM vocabulary").fetchall()
            for row in rows:
                canonical = row["canonical"]
                if canonical.lower() == raw_lower:
                    return canonical
                aliases = json.loads(row["aliases_json"])
                for alias in aliases:
                    if alias.lower().strip() == raw_lower:
                        return canonical
        return None

    def remove_vocabulary(self, canonical: str) -> None:
        """Remove a vocabulary entry."""
        with self.connection() as conn:
            conn.execute("DELETE FROM vocabulary WHERE canonical = ?", (canonical,))

    # ── Statistics ──────────────────────────────────────────────

    def get_stats(self) -> dict[str, Any]:
        """Get knowledge base statistics."""
        with self.connection() as conn:
            total = conn.execute("SELECT COUNT(*) as cnt FROM papers").fetchone()["cnt"]

            state_rows = conn.execute(
                "SELECT state, COUNT(*) as cnt FROM papers GROUP BY state"
            ).fetchall()
            by_state = {r["state"]: r["cnt"] for r in state_rows}

            year_rows = conn.execute(
                "SELECT year, COUNT(*) as cnt FROM papers WHERE year IS NOT NULL GROUP BY year ORDER BY year DESC LIMIT 10"
            ).fetchall()
            by_year = {r["year"]: r["cnt"] for r in year_rows}

            venue_rows = conn.execute(
                "SELECT venue, COUNT(*) as cnt FROM papers WHERE venue IS NOT NULL GROUP BY venue ORDER BY cnt DESC LIMIT 10"
            ).fetchall()
            by_venue = {r["venue"]: r["cnt"] for r in venue_rows}

            tag_rows = conn.execute(
                "SELECT tag, COUNT(*) as cnt FROM tags WHERE level = 'L0' GROUP BY tag ORDER BY cnt DESC"
            ).fetchall()
            by_category = {r["tag"]: r["cnt"] for r in tag_rows}

            # PDF status breakdown
            pdf_total = conn.execute(
                "SELECT COUNT(*) FROM papers WHERE pdf_path IS NOT NULL"
            ).fetchone()[0]
            parsed_total = conn.execute(
                "SELECT COUNT(*) FROM papers WHERE parsed_path IS NOT NULL"
            ).fetchone()[0]
            metadata_only = conn.execute(
                "SELECT COUNT(*) FROM papers WHERE state = 'metadata-only'"
            ).fetchone()[0]
            pdf_but_unparsed = conn.execute(
                "SELECT COUNT(*) FROM papers WHERE pdf_path IS NOT NULL AND parsed_path IS NULL"
            ).fetchone()[0]

        return {
            "total": total,
            "by_state": by_state,
            "by_year": by_year,
            "by_venue": by_venue,
            "by_category": by_category,
            "pdf_status": {
                "has_pdf": pdf_total,
                "has_parsed_text": parsed_total,
                "metadata_only": metadata_only,
                "pdf_but_unparsed": pdf_but_unparsed,
            },
        }

    # ── Summary CRUD ──────────────────────────────────────────

    def save_summary(
        self, paper_id: int, summary_text: str, model_used: str | None = None
    ) -> None:
        """Save or update a paper summary."""
        now = datetime.now(timezone.utc).isoformat()
        with self.connection() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO summaries (paper_id, summary_text, generated_at, model_used)
                   VALUES (?, ?, ?, ?)""",
                (paper_id, summary_text, now, model_used),
            )

    def get_summary(self, paper_id: int) -> dict[str, Any] | None:
        """Get a cached summary for a paper."""
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM summaries WHERE paper_id = ?", (paper_id,)
            ).fetchone()
            return dict(row) if row else None

    # ── Review CRUD ──────────────────────────────────────────

    def save_review(
        self,
        topic: str,
        review_text: str,
        paper_count: int = 0,
        scope: str | None = None,
        model_used: str | None = None,
    ) -> int:
        """Save a literature review. Returns the review ID."""
        now = datetime.now(timezone.utc).isoformat()
        with self.connection() as conn:
            cursor = conn.execute(
                """INSERT INTO reviews (topic, review_text, paper_count, scope, generated_at, model_used)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (topic, review_text, paper_count, scope, now, model_used),
            )
            return cursor.lastrowid  # type: ignore[return-value]

    def get_review(self, topic: str, scope: str | None = None) -> dict[str, Any] | None:
        """Get the most recent cached review for a topic."""
        with self.connection() as conn:
            if scope:
                row = conn.execute(
                    "SELECT * FROM reviews WHERE topic = ? AND scope = ? ORDER BY generated_at DESC LIMIT 1",
                    (topic, scope),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT * FROM reviews WHERE topic = ? AND scope IS NULL ORDER BY generated_at DESC LIMIT 1",
                    (topic,),
                ).fetchone()
            return dict(row) if row else None

    def list_reviews(self) -> list[dict[str, Any]]:
        """List all cached reviews."""
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT id, topic, paper_count, scope, generated_at FROM reviews ORDER BY generated_at DESC"
            ).fetchall()
            return [dict(r) for r in rows]

    # ── Domain Knowledge CRUD ──────────────────────────────────

    def save_domain_knowledge(
        self,
        topic: str,
        paper_id: int,
        concepts: list[str],
        methods: list[str],
        findings: list[str],
        limitations: list[str],
        relations: list[str],
    ) -> None:
        """Save or update domain knowledge for a paper within a topic."""
        now = datetime.now(timezone.utc).isoformat()
        with self.connection() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO domain_knowledge
                   (topic, paper_id, concepts_json, methods_json, findings_json,
                    limitations_json, relations_json, digested_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    topic, paper_id,
                    json.dumps(concepts), json.dumps(methods),
                    json.dumps(findings), json.dumps(limitations),
                    json.dumps(relations), now,
                ),
            )

    def get_domain_knowledge(self, topic: str) -> list[dict[str, Any]]:
        """Get all domain knowledge entries for a topic."""
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM domain_knowledge WHERE topic = ? ORDER BY paper_id",
                (topic,),
            ).fetchall()
            result = []
            for r in rows:
                d = dict(r)
                d["concepts"] = json.loads(d["concepts_json"])
                d["methods"] = json.loads(d["methods_json"])
                d["findings"] = json.loads(d["findings_json"])
                d["limitations"] = json.loads(d["limitations_json"])
                d["relations"] = json.loads(d["relations_json"])
                result.append(d)
            return result

    def get_digested_paper_ids(self, topic: str) -> set[int]:
        """Get paper IDs already digested for a topic."""
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT paper_id FROM domain_knowledge WHERE topic = ?", (topic,)
            ).fetchall()
            return {r["paper_id"] for r in rows}

    # ── Domain Report CRUD ──────────────────────────────────

    def save_domain_report(
        self,
        topic: str,
        report_text: str,
        paper_count: int = 0,
        model_used: str | None = None,
    ) -> None:
        """Save or update the domain report for a topic."""
        now = datetime.now(timezone.utc).isoformat()
        with self.connection() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO domain_reports
                   (topic, report_text, paper_count, generated_at, model_used)
                   VALUES (?, ?, ?, ?, ?)""",
                (topic, report_text, paper_count, now, model_used),
            )

    def get_domain_report(self, topic: str) -> dict[str, Any] | None:
        """Get the domain report for a topic."""
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM domain_reports WHERE topic = ?", (topic,)
            ).fetchone()
            return dict(row) if row else None

    # ── Watch Topic CRUD ───────────────────────────────────

    def add_watch_topic(
        self,
        name: str,
        queries: list[str],
        sources: list[str] | None = None,
        fetch_limit: int = 10,
        notify_channels: list[str] | None = None,
    ) -> int:
        now = datetime.now(timezone.utc).isoformat()
        queries_json = json.dumps(queries)
        sources_json = json.dumps(sources or [])
        notify_json = json.dumps(notify_channels or [])
        with self.connection() as conn:
            cursor = conn.execute(
                """INSERT INTO watch_topics
                   (name, queries_json, sources_json, fetch_limit,
                    notify_channels_json, is_active, created_at)
                   VALUES (?, ?, ?, ?, ?, 1, ?)""",
                (name, queries_json, sources_json, fetch_limit, notify_json, now),
            )
            return cursor.lastrowid  # type: ignore[return-value]

    def update_watch_topic(
        self,
        watch_id: int,
        name: str | None = None,
        queries: list[str] | None = None,
        sources: list[str] | None = None,
        fetch_limit: int | None = None,
        notify_channels: list[str] | None = None,
        is_active: bool | None = None,
    ) -> None:
        updates: list[str] = []
        params: list[Any] = []
        if name is not None:
            updates.append("name = ?")
            params.append(name)
        if queries is not None:
            updates.append("queries_json = ?")
            params.append(json.dumps(queries))
        if sources is not None:
            updates.append("sources_json = ?")
            params.append(json.dumps(sources))
        if fetch_limit is not None:
            updates.append("fetch_limit = ?")
            params.append(fetch_limit)
        if notify_channels is not None:
            updates.append("notify_channels_json = ?")
            params.append(json.dumps(notify_channels))
        if is_active is not None:
            updates.append("is_active = ?")
            params.append(1 if is_active else 0)
        if not updates:
            return
        params.append(watch_id)
        with self.connection() as conn:
            conn.execute(
                f"UPDATE watch_topics SET {', '.join(updates)} WHERE id = ?",
                params,
            )

    def touch_watch_topic(self, watch_id: int) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self.connection() as conn:
            conn.execute(
                "UPDATE watch_topics SET last_run_at = ? WHERE id = ?",
                (now, watch_id),
            )

    def delete_watch_topic(self, watch_id: int) -> None:
        with self.connection() as conn:
            conn.execute("DELETE FROM watch_topics WHERE id = ?", (watch_id,))

    def get_watch_topic(self, watch_id: int) -> dict[str, Any] | None:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM watch_topics WHERE id = ?", (watch_id,)
            ).fetchone()
            if not row:
                return None
            d = dict(row)
            d["queries"] = json.loads(d["queries_json"])
            d["sources"] = json.loads(d["sources_json"])
            d["notify_channels"] = json.loads(d["notify_channels_json"])
            return d

    def list_watch_topics(self, active_only: bool = False) -> list[dict[str, Any]]:
        with self.connection() as conn:
            if active_only:
                rows = conn.execute(
                    "SELECT * FROM watch_topics WHERE is_active = 1 ORDER BY created_at"
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM watch_topics ORDER BY created_at"
                ).fetchall()
            result = []
            for r in rows:
                d = dict(r)
                d["queries"] = json.loads(d["queries_json"])
                d["sources"] = json.loads(d["sources_json"])
                d["notify_channels"] = json.loads(d["notify_channels_json"])
                result.append(d)
            return result

    # ── Watch Log CRUD ───────────────────────────────────

    def add_watch_log(
        self,
        watch_id: int,
        papers_found: int = 0,
        papers_added: int = 0,
        notify_status: str = "none",
        error: str | None = None,
    ) -> int:
        now = datetime.now(timezone.utc).isoformat()
        with self.connection() as conn:
            cursor = conn.execute(
                """INSERT INTO watch_logs
                   (watch_id, run_at, papers_found, papers_added,
                    notify_status, error)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (watch_id, now, papers_found, papers_added, notify_status, error),
            )
            return cursor.lastrowid  # type: ignore[return-value]

    def get_watch_logs(
        self, watch_id: int, limit: int = 20
    ) -> list[dict[str, Any]]:
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM watch_logs WHERE watch_id = ? "
                "ORDER BY run_at DESC LIMIT ?",
                (watch_id, limit),
            ).fetchall()
            return [dict(r) for r in rows]
