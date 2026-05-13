---
name: paper_expert-config
description: "Load when modifying configuration, adding new config options, debugging config loading, or setting up API keys. Covers TOML config file, PaperExpertConfig dataclass, dotted key access, and library directory structure."
metadata:
  author: paper_expert-agent
  version: "1.0"
---

# Paper Expert Configuration Guide

## Config File Location

- Linux/Mac: `~/.config/paper_expert/config.toml`
- Windows: `%APPDATA%/paper_expert/config.toml`
- Override: `PaperExpertConfig.load(config_path=Path(...))`

## Full Config Reference

```toml
library_path = "~/paper_expert-library"      # 知识库根目录

[llm]
local_model = "ollama/qwen2.5"          # 本地: 分类/标签/嵌入
cloud_model = "openai/gpt-4o"           # 云端: Phase 2 QA/综述
embedding_model = "sentence-transformers/all-MiniLM-L6-v2"

[api_keys]
semantic_scholar = ""                    # 可选, 有key: 100 qps, 无key: 1 qps
openai = ""                              # Phase 2 用
anthropic = ""                           # Phase 2 用
ieee_xplore = ""                         # 可选, 200次/月
unpaywall_email = ""                     # Unpaywall 要求提供联系邮箱

[search]
default_sources = ["semantic_scholar", "openalex"]  # 可选: arxiv, ieee
default_limit = 20

[parser]
preferred = "marker"                     # "marker" (零依赖) 或 "grobid" (需Docker)
grobid_url = "http://localhost:8070"
chunk_size = 3000
chunk_overlap = 100
```

## PaperExpertConfig Dataclass (`paper_expert/core/config.py`)

```python
PaperExpertConfig
├── library_path: Path              # ~/paper_expert-library
├── llm: LLMConfig
│   ├── local_model: str
│   ├── cloud_model: str
│   └── embedding_model: str
├── api_keys: APIKeysConfig
│   ├── semantic_scholar: str
│   ├── openai: str
│   ├── anthropic: str
│   ├── ieee_xplore: str
│   └── unpaywall_email: str
├── search: SearchConfig
│   ├── default_sources: list[str]
│   └── default_limit: int
└── parser: ParserConfig
    ├── preferred: str
    ├── grobid_url: str
    ├── chunk_size: int
    └── chunk_overlap: int
```

Key methods:
- `PaperExpertConfig.load(path=None)` — load from TOML, fall back to defaults
- `config.save(path=None)` — serialize to TOML
- `config.get_nested("llm.local_model")` — dotted key read
- `config.set_nested("llm.local_model", "ollama/llama3")` — dotted key write (auto type coercion)

## Library Directory Structure

```
~/paper_expert-library/               # config.library_path
├── metadata.db                  # SQLite (source of truth)
├── vectors/
│   └── docs.pkl                 # PaperQA2 Docs pickle (rebuildable)
├── pdfs/                        # Downloaded PDF files
└── parsed/                      # Parsed structured text (Phase 2)
```

Created automatically by `Library._ensure_dirs()` on first use.

## Adding a New Config Option

1. Add field to the appropriate dataclass in `paper_expert/core/config.py`
2. Add TOML serialization in `_to_toml()`
3. Add deserialization in `_apply_dict()`
4. `set_nested` / `get_nested` work automatically for simple types
