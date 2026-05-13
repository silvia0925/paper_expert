---
name: paper_expert-review
description: "Load when working on literature review generation, research direction suggestions, domain expertise building, or the shared LLM utility. Covers ReviewEngine pipeline, DirectionAdvisor matrix, DomainExpert digestion, and llm.py."
metadata:
  author: paper_expert-agent
  version: "1.0"
---

# Paper Expert Review & Expert System (Phase 3)

## Architecture

```
scholar review "topic"        scholar suggest "topic"       scholar expert "topic"
    |                              |                              |
    v                              v                              v
Library.generate_review()     Library.suggest_directions()   Library.build_expertise()
    |                              |                              |
    v                              v                              v
ReviewEngine                  DirectionAdvisor               DomainExpert
(review_engine.py)            (direction_advisor.py)         (domain_expert.py)
    |                              |                              |
    +--------- all use ---------->+<--------- llm.py -----------+
                              (shared LLM call utility)
```

## Key Files

| File | Class | Purpose |
|------|-------|---------|
| `paper_expert/core/llm.py` | `llm_chat()`, `llm_chat_json()` | Direct OpenAI-compatible API calls (bypasses PaperQA2) |
| `paper_expert/core/review_engine.py` | `ReviewEngine` | 6-stage literature review pipeline |
| `paper_expert/core/direction_advisor.py` | `DirectionAdvisor` | Method x problem matrix + trend analysis |
| `paper_expert/core/domain_expert.py` | `DomainExpert` | Paper digestion + domain report |
| `paper_expert/models/review.py` | ReviewDocument, ResearchSuggestion, DomainReport, etc. | Data models |
| `paper_expert/cli/review.py` | `review` command | --scope, --auto-fetch, --output, --refresh |
| `paper_expert/cli/suggest.py` | `suggest` command | --trends |
| `paper_expert/cli/expert.py` | `expert` command | --update, --ask |

## LLM Call Utility (`paper_expert/core/llm.py`)

All Phase 3 engines bypass PaperQA2 and call the LLM directly via httpx:

```python
# Text response
text = await llm_chat(messages, config=config, temperature=0.3, max_tokens=4096)

# JSON response (auto-parses, strips ```json blocks)
data = await llm_chat_json(messages, config=config)
```

- Reads `api_keys.openai` + `llm.api_base` + `llm.cloud_model` from config
- Strips "openai/" prefix from model name for raw API calls
- Retry with exponential backoff (base 3s, max 4 retries) for rate-limited proxies

## ReviewEngine — 6-Stage Pipeline

```
Stage 1: Topic Analysis (1 LLM call)
  Input: topic string
  Output: keywords[], sub_themes[], scope_description

Stage 2: Paper Retrieval (0 LLM, SQLite LIKE query)
  Input: expanded keywords
  Output: up to 30 papers sorted by citation count

Stage 3: Paper Grouping (1 LLM call)
  Input: all paper abstracts
  Output: 3-6 groups with paper indices

Stage 4: Per-Group Analysis (N LLM calls, 1/group)
  Input: group papers
  Output: methods, arguments, comparisons per group

Stage 5: Cross-Group Synthesis (1 LLM call)
  Input: all group analyses
  Output: agreements, contradictions, trends

Stage 6: Document Assembly (2 LLM calls)
  Input: all above + references
  Output: Markdown review with 6 sections
```

Caching: saves to `reviews` table in SQLite. Same topic returns cached unless `--refresh`.
Auto-fetch: if <5 papers found, searches external sources before generating.

## DirectionAdvisor — Gap Analysis

```
1. Get topic papers from SQLite
2. LLM extracts methods[] and problems[] from paper abstracts
3. Build co-occurrence matrix (method x problem -> paper count)
4. Empty cells = gaps (e.g. "KAN + ILT")
5. Trend detection: group papers by year, compare early vs late half
6. LLM generates 3-5 suggestions from gaps + trends
```

Output: `DirectionReport` with suggestions, trends, matrix_gaps.

## DomainExpert — Knowledge Building

Two phases:
1. **Digestion**: For each paper, LLM extracts concepts/methods/findings/limitations/relations -> `domain_knowledge` table
2. **Report**: Synthesize all entries into a structured report (Concept Map, Method Evolution, Key Debates, Landmark Papers, State of the Art) -> `domain_reports` table

Incremental: `get_digested_paper_ids()` checks what's done, only new papers get digested.
Expert QA: `--ask` builds context from domain knowledge + relevant entries, feeds to LLM for expert-level answer.

## Database Tables (v3)

```sql
reviews (id, topic, review_text, paper_count, scope, generated_at, model_used)
domain_knowledge (id, topic, paper_id, concepts_json, methods_json, findings_json, limitations_json, relations_json, digested_at)
domain_reports (id, topic UNIQUE, report_text, paper_count, generated_at, model_used)
```

## Cost Estimates

| Operation | LLM Calls | Estimated Cost |
|-----------|-----------|---------------|
| Review (10 papers, 4 groups) | ~8 calls | $0.05-0.20 |
| Suggest (20 papers) | ~2 calls | $0.02-0.05 |
| Expert digest (20 papers) | ~20 calls | $0.10-0.40 |
| Expert report | ~1 call | $0.01-0.03 |
| Expert Q&A | ~1 call | $0.01-0.02 |
