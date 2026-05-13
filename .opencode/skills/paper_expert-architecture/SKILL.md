---
name: paper_expert-architecture
description: "Load when working on cross-module changes, understanding data flow, or debugging component interactions. Covers Library orchestrator, component relationships, async patterns, and persistence strategy."
metadata:
  author: paper_expert-agent
  version: "1.0"
---

# Paper Expert Architecture Deep Dive

## Component Graph

```
CLI (Typer, sync entry)
 │  asyncio.run()
 ▼
Library (paper_expert/core/library.py)
 ├── .db           → Database (paper_expert/core/database.py)
 │                    SQLite: papers, tags, citations, vocabulary
 ├── .paperqa      → PaperQAAdapter (paper_expert/adapters/paperqa.py)
 │                    PaperQA2 Docs: parse, chunk, vectorize, serialize
 ├── .search_engine → SearchAggregator (paper_expert/core/search.py)
 │                    ├── SemanticScholarAdapter
 │                    ├── OpenAlexAdapter
 │                    ├── ArxivAdapter
 │                    └── IEEEAdapter
 ├── .pdf_fetcher  → PDFFetcher (paper_expert/core/pdf_fetcher.py)
 │                    Waterfall: arXiv → S2 OA → Unpaywall
 └── ._s2          → SemanticScholarAdapter (citations only)
```

## Key Data Flows

### add_paper (the most complex flow)
```python
async Library.add_paper(metadata, pdf_path=None, auto_classify=True):
    1. Check duplicate by DOI → return existing if found
    2. If no pdf_path → PDFFetcher.fetch(metadata)  # waterfall
    3. Determine state: full-text if PDF, else metadata-only
    4. If PDF + PaperQA available → PaperQAAdapter.add_document(pdf, title)
    5. Database.add_paper(...)  → paper_id
    6. classifier.classify_paper(db, paper_id, metadata)  # L0 sync
    7. _save_citations(paper_id, metadata)  # fetch S2 refs, create stubs
    8. Return Paper.from_db_row(...)
```

### search (parallel multi-source)
```python
async Library.search(query, sources, limit, year):
    1. SearchAggregator.search() → fires asyncio.create_task per source
    2. asyncio.gather(*tasks, return_exceptions=True)
    3. _deduplicate() by DOI (S2 preferred) then by title
    4. Mark in_library for each result
```

### Persistence Model (dual storage)
```
SQLite (metadata.db)          PaperQA2 (vectors/docs.pkl)
━━━━━━━━━━━━━━━━━━━          ━━━━━━━━━━━━━━━━━━━━━━━━━━
papers table                  Docs.docs (dict)
tags table                    Docs.texts (list of chunks)
citations table               Docs.texts_index (vectors)
vocabulary table              
summaries table (P2)          

SOURCE OF TRUTH               REBUILDABLE from SQLite + PDFs
write on every add            save() after add_document()
survives PaperQA2 upgrade     may break on PaperQA2 upgrade
query via SQL                 query via Docs.aquery()
```

### ask (Phase 2 — QA with optional auto-fetch)
```python
async Library.ask(question, scope=None, auto_fetch=False, ...):
    # auto_fetch=False:
    1. QAEngine(paperqa, db).ask(question, scope)
       → PaperQAAdapter.query(question) → Docs.aquery()
       → assess_confidence(contexts) → QAAnswer

    # auto_fetch=True:
    1. AutoFetcher(qa_engine, library).ask_with_fetch(question, ...)
       → ask → insufficient? → derive_search_queries (Ollama)
       → Library.search() → Library.add_paper() → retry ask
       → up to max_iterations
```

For full QA details → load `paper_expert-qa` skill.

## Async Pattern
- All network I/O is async (httpx.AsyncClient)
- CLI bridges with `asyncio.run()` in each command
- PaperQA2's `Docs.aadd()` is async
- Database is sync (sqlite3) — called within async context without issues for single-user

## Error Handling Strategy
- Network errors → log + continue (metadata-only fallback)
- PaperQA2 unavailable → search/metadata still work, vectorization disabled
- Ollama unavailable → L0 keyword classification still works, L1 skipped
- Corrupt pickle → auto-recreate fresh Docs, log warning

## Adding a New Component
1. Create the module in the appropriate package
2. If it's an external API → goes in `adapters/`
3. Wire it into `Library.__init__()` if needed at Library level
4. If async → follow the httpx.AsyncClient pattern (see semantic_scholar.py)
5. Add cleanup to `Library.close()` if the component holds connections
