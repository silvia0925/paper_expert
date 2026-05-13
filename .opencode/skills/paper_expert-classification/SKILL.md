---
name: paper_expert-classification
description: "Load when working on paper classification, tag management, controlled vocabulary, or LLM integration for auto-tagging. Covers three-tier system, keyword rules, Ollama LLM calls, vocabulary normalization."
metadata:
  author: paper_expert
  version: "2.0"
---

# Paper Expert Classification System

## Three-Tier Architecture (Domain-Agnostic)

```
L0: Domain Classification (keyword rules, no LLM)
    Uses DomainConfig.l0_keywords — user-defined keyword groups
    Match logic: check each group's keywords against title+abstract
    Two+ groups matched → "Cross-domain"
    One group → group name
    None → "Other"

L1: Sub-topic Classification (Ollama LLM + controlled vocabulary)
    Uses DomainConfig.l1_prompt_template + build_l1_prompt()
    Normalized tags → matched against vocabulary
    Suggested tags → new terms tracked for vocabulary promotion

L2: User Tags (manual only, free-form)
    └── "to-read", "important", "weak-baseline", ...
```

## L0 Keyword Groups (paper_expert/core/classifier.py)

**No hardcoded keywords.** All L0 keyword groups come from `DomainConfig.l0_keywords`.
Classification logic in `classify_l0(title, abstract, domain_config)`:
- If domain_config is None or has no keywords → returns ["Other"]
- Each group's keywords checked against lowercased title+abstract
- Two+ groups match → "Cross-domain"
- One group matches → that group's name
- None → "Other"

To configure: use CLI `paper_expert domain init/add-keyword` or MCP `setup_domain/add_domain_keyword`.

## L1 LLM Classification Flow

```
Paper (title + abstract)
    │
    ▼
build_l1_prompt(domain_config, title, abstract)
    Fills {domain_name}, {vocab_summary}, {title}, {abstract}
    into domain_config.l1_prompt_template
    │
    ▼
Ollama API (POST /api/generate)
    model: config.llm.local_model (strip "ollama/" prefix)
    format: "json" (expects JSON array output)
    │
    ▼
normalize_l1_tags(raw_tags, db)
    │
    ├── Known → matched against db vocabulary → confidence=0.8
    └── Unknown → stored as suggested=1 (accumulate for promotion)
```

## Controlled Vocabulary (paper_expert/core/vocabulary.py)

**No default vocabulary.** Starts empty. Populated by:
1. User-defined via `DomainConfig.l1_vocabulary`
2. `init_vocabulary(db, domain_config=config.domain)` — syncs DomainConfig to SQLite
3. Growth via suggested tag promotion

### Vocabulary Promotion Flow
1. LLM generates unrecognized tag → stored as `suggested=1`
2. `check_suggested_tags(db, threshold=3)` finds tags with 3+ papers
3. User promotes: `paper_expert domain add-vocab "Tag" "alias1, alias2"`
4. Re-sync: `init_vocabulary(db, domain_config=config.domain)`

## Key Files

| File | Role |
|------|------|
| `paper_expert/core/domain.py` | DomainConfig + init + prompt building |
| `paper_expert/core/classifier.py` | classify_l0, classify_l1_llm, normalize_l1_tags, classify_paper_full |
| `paper_expert/core/vocabulary.py` | init_vocabulary, export_vocabulary, check_suggested_tags |

## Sync vs Async

- `classify_paper(db, paper_id, metadata, domain_config)` — SYNC, L0 only
- `classify_paper_full(db, paper_id, metadata, domain_config, model)` — ASYNC, L0 + L1
- `batch_classify(db, domain_config, model)` — ASYNC, all untagged papers

## Ollama Failure Handling

If Ollama is not running:
- `httpx.ConnectError` caught → warning logged → L1 tags empty
- Paper gets L0 tags only
- Retry later: `paper_expert lib classify`