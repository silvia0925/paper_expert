# Paper Expert

Universal AI-powered academic research assistant with **user-defined domain configuration**.

Unlike domain-specific research tools, Paper Expert lets you define your own research direction — keywords, vocabulary, and classification prompts — so it adapts to any field, from quantum computing to bioinformatics to social sciences.

## Features

- **User-defined research domain**: Configure your own keyword groups, vocabulary, and classification prompts
- **Multi-source search**: Semantic Scholar, OpenAlex, arXiv, IEEE Xplore
- **Smart PDF acquisition**: Automatic waterfall strategy (arXiv -> S2 OA -> Unpaywall)
- **Persistent knowledge base**: SQLite metadata + PaperQA2 vector index
- **Three-tier classification**: Domain keywords (L0) + LLM sub-topics (L1) + free tags (L2)
- **Citation graph**: Store and traverse citation relationships
- **Bulk import**: Zotero, BibTeX, local PDF directories
- **Literature review**: Automated multi-stage review generation
- **Domain expertise**: Systematic knowledge building from paper reading
- **Research direction suggestions**: Method x problem gap analysis

## Installation

```bash
pip install -e .
```

For development:

```bash
pip install -e ".[dev]"
```

## Quick Start

```bash
# Step 1: Set up your research domain (required for classification)
paper-expert domain init "Quantum Computing" --keywords '{"Quantum": ["qubit", "quantum gate", "entanglement"], "ML": ["neural", "deep learning"]}'

# Step 2: Configure your library
paper-expert config set library_path ~/paper-expert-library
paper-expert config set api_keys.unpaywall_email your@email.com

# Step 3: Search and add papers
paper-expert search "quantum error correction"
paper-expert add arxiv:2401.12345
paper-expert add doi:10.1234/example

# Step 4: Build domain knowledge
paper-expert domain add-keyword Quantum "superposition"
paper-expert domain add-vocab QNN "Quantum Neural Network, Quantum NN"

# Browse and analyze
paper-expert lib list
paper-expert lib stats
paper-expert review "quantum error correction"
paper-expert suggest "quantum computing"
paper-expert expert "quantum computing"
```

## Domain Configuration

The key difference from Scholar Agent: **no hardcoded domains**. You define everything.

### CLI Commands

```bash
# Initialize a new research domain
paper-expert domain init <name> --keywords '<json>'

# View current domain configuration
paper-expert domain show

# Add keywords to domain groups
paper-expert domain add-keyword <group> <keyword>

# Add vocabulary entries for tag normalization
paper-expert domain add-vocab <canonical> <aliases>
```

### MCP Tools (for OpenCode / Claude Desktop)

- `setup_domain(domain_name, keywords_json)` — Create or change your research domain
- `get_domain_config()` — View current domain settings
- `add_domain_keyword(group, keyword)` — Add L0 classification keywords
- `add_domain_vocab(canonical, aliases)` — Add vocabulary for L1 normalization

## Configuration

Config file: `~/.config/paper_expert/config.toml` (Linux/Mac) or `%APPDATA%/paper_expert/config.toml` (Windows)

```toml
library_path = "~/paper-expert-library"

[domain]
domain_name = "Quantum Computing"

[domain.l0_keywords]
Quantum = ["qubit", "quantum gate", "entanglement"]
ML = ["neural", "deep learning"]

[domain.l1_vocabulary]
QNN = ["Quantum Neural Network", "Quantum NN"]

[llm]
local_model = "ollama/qwen2.5"
cloud_model = "openai/gpt-4o"
embedding_model = "sentence-transformers/all-MiniLM-L6-v2"

[api_keys]
semantic_scholar = ""
openai = ""
unpaywall_email = "your@email.com"

[search]
default_sources = ["semantic_scholar", "openalex"]
default_limit = 20

[parser]
preferred = "marker"
chunk_size = 3000
```

## Architecture

```
paper_expert/
├── cli/          # Typer CLI commands (including domain management)
├── core/         # Business logic (library, search, classifier, database, domain)
├── adapters/     # External API adapters (S2, OpenAlex, arXiv, IEEE, PaperQA2)
├── importers/    # Bulk import (Zotero, BibTeX, directory)
└── models/       # Pydantic data models
```

## Differences from Scholar Agent

- **No hardcoded domains**: All vocabulary, keywords, and classification prompts are user-defined
- **Domain setup wizard**: CLI and MCP tools to configure your research direction
- **Empty vocabulary by default**: Grows as you add papers and define terms
- **Domain-agnostic classifier**: L0 and L1 classification uses your domain config, not hardcoded AI/lithography terms

## License

MIT