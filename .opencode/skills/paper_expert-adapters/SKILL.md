---
name: paper_expert-adapters
description: "Load when adding new external API adapters, modifying search providers, or debugging API integration issues. Covers adapter pattern, rate limiting, error handling, and how to add a new source."
metadata:
  author: paper_expert-agent
  version: "1.0"
---

# Paper Expert Adapters Guide

## Adapter Pattern

All adapters in `paper_expert/adapters/` follow the same pattern:

```python
class SomeAdapter:
    def __init__(self, config_or_params):
        self._client = httpx.AsyncClient(
            base_url="https://api.example.com",
            headers={...},
            timeout=30.0,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def search(self, query, **kwargs) -> list[SearchResult]:
        ...

    def _to_search_result(self, raw_data) -> SearchResult:
        # Convert API-specific format to our unified model
        ...
```

Key rules:
- Each adapter owns its own `httpx.AsyncClient`
- `close()` must be called (Library.close handles this)
- Return types are always our models (`SearchResult`, `PaperMetadata`)
- Rate limit handling is adapter-specific

## Existing Adapters

### SemanticScholarAdapter (`semantic_scholar.py`)
- **Base URL**: `https://api.semanticscholar.org/graph/v1`
- **Auth**: Optional API key via `x-api-key` header
- **Rate limit**: 1 req/s (no key) or 100 req/s (with key)
- **Retry**: Exponential backoff on 429, max 3 retries
- **Methods**: `search()`, `get_paper(id)`, `get_references(id)`, `get_citations(id)`
- **ID formats**: S2 ID, `DOI:xxx`, `ARXIV:xxx`

### OpenAlexAdapter (`openalex.py`)
- **Base URL**: `https://api.openalex.org`
- **Auth**: None needed; `mailto` param for polite pool
- **Rate limit**: Generous (10 req/s polite pool)
- **Special**: Abstract comes as inverted index → `_reconstruct_abstract()` reassembles it
- **Methods**: `search()`, `get_work(id)`, `get_work_by_doi(doi)`

### ArxivAdapter (`arxiv.py`)
- **Base URL**: `https://export.arxiv.org/api/query` (MUST be HTTPS)
- **Auth**: None
- **Rate limit**: 1 req/3s recommended
- **Special**: Returns Atom XML → parsed with `xml.etree.ElementTree`
- **Methods**: `search()`, `get_by_id(arxiv_id)`, `pdf_url(arxiv_id)` (static)

### IEEEAdapter (`ieee.py`)
- **Base URL**: `https://ieeexploreapi.ieee.org/api/v1/search/articles`
- **Auth**: API key required (200 req/month free tier)
- **Methods**: `search()` — only enabled when key is configured
- **Property**: `.available` → False if no key

### PaperQAAdapter (`paperqa.py`)
- **Special**: Not an API adapter — wraps PaperQA2's `Docs` class
- **CRITICAL**: Only module allowed to `import paperqa`
- **Persistence**: pickle to `vectors/docs.pkl`
- **Graceful degradation**: If PaperQA2 unavailable, `.available` is False

## How to Add a New Search Source

1. Create `paper_expert/adapters/new_source.py`:
   ```python
   class NewSourceAdapter:
       def __init__(self, ...):
           self._client = httpx.AsyncClient(...)
       async def close(self): ...
       async def search(self, query, limit, ...) -> list[SearchResult]: ...
   ```

2. Register in `SearchAggregator` (`paper_expert/core/search.py`):
   - Add to `__init__` 
   - Add case to `_search_source()` match statement
   - Add to `close()` gather

3. Add source name to `PaperExpertConfig.search.default_sources` options

4. Test: mock the API responses in `tests/`

## SearchAggregator Deduplication Logic

```python
# Priority: S2 > OpenAlex > arXiv > IEEE
results.sort(key=lambda r: r.source != "semantic_scholar")

# Dedup by DOI first (exact), then by normalized title
# If duplicate found from different source, merge missing fields:
#   - Fill abstract if primary source lacked it
#   - Fill open_access_pdf_url if primary source lacked it
```
