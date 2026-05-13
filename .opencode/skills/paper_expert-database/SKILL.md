---
name: paper_expert-database
description: "Load when modifying the SQLite schema, adding new queries, implementing migrations, or debugging data issues. Covers schema, CRUD patterns, migration strategy, and query optimization."
metadata:
  author: paper_expert-agent
  version: "1.0"
---

# Paper Expert Database Guide

## Schema (v3)

```sql
papers (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    doi             TEXT UNIQUE,           -- can be NULL for arXiv-only papers
    title           TEXT NOT NULL,
    authors_json    TEXT DEFAULT '[]',     -- JSON array of strings
    year            INTEGER,
    venue           TEXT,
    abstract        TEXT,
    source          TEXT DEFAULT 'manual', -- enum: semantic_scholar|openalex|arxiv|ieee|manual|zotero|bibtex
    state           TEXT DEFAULT 'pending',-- enum: full-text|metadata-only|pending
    arxiv_id        TEXT,
    s2_paper_id     TEXT,
    citation_count  INTEGER DEFAULT 0,
    pdf_path        TEXT,                  -- absolute path to PDF
    parsed_path     TEXT,                  -- absolute path to parsed text (Phase 2)
    date_added      TEXT NOT NULL          -- ISO 8601 UTC
)

tags (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    paper_id    INTEGER NOT NULL → papers(id) ON DELETE CASCADE,
    level       TEXT CHECK (level IN ('L0','L1','L2')),
    tag         TEXT NOT NULL,
    confidence  REAL,                      -- 0-1, NULL for manual tags
    suggested   INTEGER DEFAULT 0,         -- 1 = not yet in vocabulary
    UNIQUE (paper_id, level, tag)
)

citations (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    citing_paper_id   INTEGER NOT NULL → papers(id) ON DELETE CASCADE,
    cited_paper_id    INTEGER NOT NULL → papers(id) ON DELETE CASCADE,
    UNIQUE (citing_paper_id, cited_paper_id)
)

vocabulary (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical     TEXT NOT NULL UNIQUE,    -- e.g. "GAN"
    aliases_json  TEXT DEFAULT '[]'        -- JSON array: ["Generative Adversarial Network", "GANs"]
)

summaries (                               -- Added in v2
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    paper_id      INTEGER NOT NULL UNIQUE, -- FK → papers(id) ON DELETE CASCADE
    summary_text  TEXT NOT NULL,
    generated_at  TEXT NOT NULL,           -- ISO 8601 UTC
    model_used    TEXT                     -- e.g. "openai/gpt-4o"
)
```

## Indexes
```sql
idx_papers_doi, idx_papers_s2_paper_id, idx_papers_arxiv_id,
idx_papers_state, idx_papers_year,
idx_tags_paper_id, idx_tags_tag,
idx_citations_citing, idx_citations_cited
```

## Connection Pattern

```python
# Every operation gets its own connection (no long-lived connection)
with self.connection() as conn:
    conn.execute(...)
    # auto-commit on exit, auto-rollback on exception
```

PRAGMAs set per connection: `journal_mode=WAL`, `foreign_keys=ON`

## CRUD Methods Quick Reference

### Papers
| Method | Signature | Returns |
|--------|-----------|---------|
| `add_paper(title, doi=, authors=, ...)` | All fields optional except title | `int` (paper_id) |
| `get_paper(paper_id)` | By ID | `dict \| None` |
| `get_paper_by_doi(doi)` | By DOI | `dict \| None` |
| `get_paper_by_s2_id(s2_paper_id)` | By S2 ID | `dict \| None` |
| `update_paper(paper_id, **kwargs)` | Any allowed fields | `None` |
| `delete_paper(paper_id)` | Cascades to tags/citations | `None` |
| `list_papers(state=, year=, tag=, sort_by=, limit=, offset=)` | All filters optional | `list[dict]` |
| `count_papers(state=)` | | `int` |
| `paper_exists(doi=, title=)` | Check by DOI or exact title | `bool` |

### Tags
| Method | Notes |
|--------|-------|
| `add_tag(paper_id, level, tag, confidence=, suggested=)` | INSERT OR IGNORE |
| `remove_tag(paper_id, tag)` | By paper + tag text |
| `get_tags(paper_id, level=)` | Filter by level optional |
| `get_suggested_tag_counts()` | For vocabulary promotion |
| `get_untagged_paper_ids(level="L1")` | For batch classification |

### Citations
| Method | Notes |
|--------|-------|
| `add_citation(citing, cited)` | INSERT OR IGNORE |
| `get_references(paper_id)` | Outgoing (this paper cites) |
| `get_citations(paper_id)` | Incoming (citing this paper) |

### Vocabulary
| Method | Notes |
|--------|-------|
| `add_vocabulary(canonical, aliases)` | INSERT OR REPLACE |
| `normalize_tag(raw_tag)` | Returns canonical or None |
| `get_vocabulary()` | All entries |
| `remove_vocabulary(canonical)` | |

### Summaries (added in v2)
| Method | Notes |
|--------|-------|
| `save_summary(paper_id, text, model)` | INSERT OR REPLACE (upserts) |
| `get_summary(paper_id)` | Returns dict or None |

### Reviews (added in v3)
| Method | Notes |
|--------|-------|
| `save_review(topic, text, paper_count, scope, model)` | Returns review ID |
| `get_review(topic, scope=)` | Most recent cached review |
| `list_reviews()` | All reviews |

### Domain Knowledge (added in v3)
| Method | Notes |
|--------|-------|
| `save_domain_knowledge(topic, paper_id, concepts, methods, ...)` | Upserts by (topic, paper_id) |
| `get_domain_knowledge(topic)` | All entries (auto-parses JSON) |
| `get_digested_paper_ids(topic)` | Set of digested paper IDs |

### Domain Reports (added in v3)
| Method | Notes |
|--------|-------|
| `save_domain_report(topic, text, paper_count, model)` | Upserts by topic |
| `get_domain_report(topic)` | Returns dict or None |

## Migration Strategy

Current: `_SCHEMA_VERSION = 3` stored in `schema_version` table.
- **v1 → v2**: Added `summaries` table.
- **v2 → v3**: Added `reviews`, `domain_knowledge`, `domain_reports` tables.

When schema changes:
1. Bump `_SCHEMA_VERSION`
2. Add migration SQL in `_init_db()` checking current version
3. ALTER TABLE or create new tables as needed
4. Update version in `schema_version` table

## Important: authors are JSON

`authors_json` stores a JSON array string: `'["Alice Smith", "Bob Jones"]'`
When updating, use: `db.update_paper(id, authors=["Alice", "Bob"])` — the method auto-converts to JSON.
When reading, `Paper.from_db_row()` auto-parses back to `list[str]`.
