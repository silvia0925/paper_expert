---
name: paper_expert-known-issues
description: "Load when debugging runtime errors, encountering unexpected behavior, or working around platform-specific issues. Covers all known bugs, workarounds, and their locations in the codebase."
metadata:
  author: paper_expert-agent
  version: "1.0"
---

# Paper Expert Known Issues & Workarounds

## Active Issues

### 1. PaperQA2 Settings env var conflict
- **Symptom**: `ValidationError: agent - Input should be AgentSettings, got int`
- **Cause**: Environment variable `AGENT=1` (from opencode) gets picked up by pydantic-settings
- **Workaround**: `adapters/paperqa.py` clears `AGENT` env var before retrying Settings init. If still fails, PaperQA2 is disabled (search/metadata still work).
- **Location**: `paper_expert/adapters/paperqa.py` → `_build_settings()`

### 2. Windows GBK terminal encoding
- **Symptom**: `UnicodeEncodeError: 'gbk' codec can't encode character`
- **Cause**: Rich tries to render Unicode symbols (checkmarks, crosses, special chars in paper titles) on Windows GBK terminal
- **Workaround**: 
  - Tables use Y/N instead of checkmarks/crosses
  - Paper titles: `re.sub(r"<[^>]+>", "", title)` strips HTML tags, `.encode("ascii","replace").decode("ascii")` removes non-ASCII
- **Location**: `paper_expert/cli/search.py`, `paper_expert/cli/read.py`

### 3. bibtexparser version compatibility
- **Symptom**: `bibtexparser>=2` not installable (v2 is still beta)
- **Workaround**: Pin `>=1.4`, code detects version at import time (`_HAS_V2 = hasattr(bibtexparser, "parse")`) and uses the appropriate API
- **Location**: `paper_expert/importers/bibtex.py`

### 4. arXiv API HTTPS redirect
- **Symptom**: `301 Moved Permanently` when hitting arXiv API
- **Workaround**: Use `https://` directly instead of `http://`
- **Location**: `paper_expert/adapters/arxiv.py` → `ARXIV_API_BASE`

### 5. Semantic Scholar rate limiting without API key
- **Symptom**: Repeated `429` responses, slow searches
- **Cause**: Without API key, S2 allows only 1 req/s
- **Workaround**: Exponential backoff (2s → 4s → 8s, max 3 retries). Configure API key for 100 qps: `scholar config set api_keys.semantic_scholar YOUR_KEY`
- **Location**: `paper_expert/adapters/semantic_scholar.py` → `_request()`

## Platform Notes

- **Windows**: GBK encoding issues (see #2). Always test Rich output on Windows.
- **GROBID**: Requires Docker. Default parser is `marker` (pure Python). Switch via `scholar config set parser.preferred grobid`.
- **Ollama**: Must be running locally for L1 classification. If unavailable, L0 keyword classification still works.

## Dependency Pins

| Package | Pin | Reason |
|---------|-----|--------|
| `paper-qa` | `>=5` | Major API change at v5 |
| `bibtexparser` | `>=1.4` | v2 beta incompatible, code handles both |
| `typer` | `>=0.12` | `[all]` extra deprecated in 0.24+ (harmless warning) |
