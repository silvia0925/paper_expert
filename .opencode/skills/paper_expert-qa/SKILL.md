---
name: paper_expert-qa
description: "Load when working on QA question answering, auto-fetch, confidence assessment, paper summaries, or the ask command. Covers QAEngine, AutoFetcher, scope filtering, confidence thresholds, and summary caching."
metadata:
  author: paper_expert-agent
  version: "1.0"
---

# Paper Expert QA System (Phase 2)

## Architecture

```
scholar ask "question" --auto-fetch
    │
    ▼
Library.ask(question, auto_fetch=True)
    │
    ├── auto_fetch=False → QAEngine.ask(question, scope)
    │                        │
    │                        ├── parse scope → query SQLite for paper IDs
    │                        ├── PaperQAAdapter.query(question) → raw dict
    │                        ├── assess_confidence(contexts) → level + is_sufficient
    │                        └── return QAAnswer
    │
    └── auto_fetch=True → AutoFetcher.ask_with_fetch(question, ...)
                            │
                            ├── 1. QAEngine.ask(question) → answer
                            ├── 2. is_sufficient? → return
                            ├── 3. derive_search_queries(question, answer) via Ollama
                            ├── 4. Library.search(derived_query)
                            ├── 5. Library.add_paper(result) for each
                            ├── 6. QAEngine.ask(question) → retry
                            └── 7. repeat up to max_iterations (default 3)
```

## Key Files

| File | Class/Function | Purpose |
|------|---------------|---------|
| `paper_expert/core/qa_engine.py` | `QAEngine` | Core QA: ask + summarize |
| `paper_expert/core/qa_engine.py` | `assess_confidence()` | Classify answer confidence |
| `paper_expert/core/qa_engine.py` | `parse_scope()` | Parse "tag:OPC" style filters |
| `paper_expert/core/auto_fetch.py` | `AutoFetcher` | Fetch-retry loop orchestrator |
| `paper_expert/core/auto_fetch.py` | `derive_search_queries()` | LLM-based search query generation |
| `paper_expert/adapters/paperqa.py` | `.query()` | PaperQA2 Docs.aquery wrapper |
| `paper_expert/adapters/paperqa.py` | `.summarize()` | Paper summary via PaperQA2 |
| `paper_expert/models/qa.py` | `QAAnswer`, `QASource` | Response models |
| `paper_expert/cli/ask.py` | `ask` command | CLI entry point |

## QAAnswer Model

```python
QAAnswer(
    answer: str,           # Generated answer text
    question: str,         # Original question
    sources: list[QASource],  # Cited passages with paper info
    cost: float,           # LLM API cost ($)
    confidence: ConfidenceLevel,  # HIGH / MEDIUM / LOW
    is_sufficient: bool,   # True if evidence is adequate
    error: str | None,     # Error message if failed
)

QASource(
    paper_id: int | None,  # Database paper ID (resolved from doc_name)
    paper_title: str,
    year: int | None,
    passage: str,          # Text excerpt used as evidence
    relevance_score: float,  # 0-1, from PaperQA2 retrieval
)
```

## Confidence Assessment

Thresholds (in `qa_engine.py`):
```python
_MIN_CONTEXTS_FOR_SUFFICIENT = 2    # Need at least 2 relevant passages
_HIGH_CONFIDENCE_MIN_SCORE = 0.7    # Average score >= 0.7 → HIGH
_MEDIUM_CONFIDENCE_MIN_SCORE = 0.4  # Average score >= 0.4 → MEDIUM
                                     # Below → LOW
```

Logic:
- < 2 contexts → LOW, not sufficient (triggers auto-fetch if enabled)
- >= 2 contexts + avg score >= 0.7 → HIGH, sufficient
- >= 2 contexts + avg score >= 0.4 → MEDIUM, sufficient
- >= 2 contexts + avg score < 0.4 → LOW, not sufficient

## Scope Filtering

Format: `"tag:OPC"`, `"year:2024-2025"`, `"tag:GAN, year:2024"`

Parsed by `parse_scope()` → `{"tag": "OPC"}` → `_get_scoped_paper_ids(db, ...)` queries SQLite.

**Current limitation**: Scope identifies matching paper IDs but queries run against full Docs. True doc-level filtering in PaperQA2 requires further investigation (marked as TODO in code).

## Auto-Fetch Loop

```
Iteration 0: query existing → insufficient
Iteration 1: derive queries → search → add N papers → retry → still insufficient
Iteration 2: derive queries → search → add N papers → retry → sufficient → return
```

Controls:
- `fetch_limit`: max papers per iteration (default 5)
- `max_iterations`: max retry cycles (default 3)
- Stops early if: answer sufficient, no new papers found, or error

Search query derivation uses Ollama (local LLM) with prompt that includes original question + insufficient answer. Falls back to original question if Ollama unavailable.

## Summary Generation + Caching

`QAEngine.summarize_paper(paper_id)`:
1. Check `summaries` table in SQLite (cache)
2. If cached → return
3. If not → PaperQAAdapter.summarize(title) → structured prompt asking for objective/method/findings/limitations
4. Cache result in SQLite with model_used and timestamp

Summary requires: full-text paper (has PDF + vectorized) + cloud LLM API key.

## PaperQA Adapter Query Interface

```python
# Returns a plain dict (not PaperQA2 types — isolation!)
adapter.query(question, settings_override=None) -> {
    "answer": str,
    "question": str,
    "references": str,       # Formatted reference list
    "contexts": [             # Retrieved passages
        {"text": str, "score": float, "doc_name": str},
        ...
    ],
    "cost": float,
    "error": str | None,
}
```

Error cases return dict with `error` set, never raises. QAEngine wraps this into QAAnswer model.

## Prerequisites for QA

Users must configure a cloud LLM API key:
```bash
scholar config set api_keys.openai sk-xxx
# or
scholar config set api_keys.anthropic sk-ant-xxx
```

CLI validates this before attempting QA and shows clear instructions if missing.
