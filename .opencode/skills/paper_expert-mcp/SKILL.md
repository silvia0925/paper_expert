---
name: paper_expert-mcp
description: "Load when modifying MCP tools, adding new MCP functionality, debugging MCP server issues, or configuring OpenCode/Claude Desktop integration. Covers FastMCP patterns, tool registration, transport, and dual-entry architecture."
metadata:
  author: paper_expert-agent
  version: "1.0"
---

# Paper Expert MCP Server

## Overview

`paper_expert/mcp_server.py` exposes scholar's capabilities as MCP tools. It imports the same `Library` class that the CLI uses — zero code duplication.

```
mcp_server.py
  |
  +-- FastMCP("Paper Expert")
  |     |
  |     +-- @mcp.tool() search_papers(...)
  |     +-- @mcp.tool() add_paper(...)
  |     +-- @mcp.tool() list_papers(...)
  |     +-- @mcp.tool() get_paper(...)
  |     +-- @mcp.tool() tag_paper(...)
  |     +-- @mcp.tool() get_stats()
  |     +-- @mcp.tool() ask_question(...)
  |     +-- @mcp.tool() generate_review(...)
  |     +-- @mcp.tool() suggest_directions(...)
  |     +-- @mcp.tool() build_expertise(...)
  |
  +-- _get_library() → lazy singleton Library instance
  |
  +-- main() → mcp.run(transport="stdio")
```

## Tool Pattern

```python
@mcp.tool()
async def tool_name(arg1: str, arg2: int = 10) -> str:
    """Tool description shown to the AI.

    Args:
        arg1: Description of arg1.
        arg2: Description of arg2.

    Returns:
        JSON string or Markdown text.
    """
    lib = _get_library()
    result = await lib.some_method(arg1, arg2)
    return json.dumps(result, ensure_ascii=False, indent=2)
```

Rules:
- All tools are `async`
- Return `str` (JSON or Markdown) — never Python objects
- Use `_get_library()` for lazy Library singleton
- Docstring becomes the tool description AI sees — be clear and specific
- Type hints on args become the tool's input schema

## 10 Registered Tools

| Tool | Maps to | Returns |
|------|---------|---------|
| `search_papers(query, limit, year, source)` | `Library.search()` | JSON array of papers |
| `add_paper(identifier)` | `Library.add_by_identifier()` | Confirmation text |
| `list_papers(tag, year, state, sort_by, limit)` | `Library.list_papers()` | JSON array |
| `get_paper(paper_id)` | `Library.get_paper()` | JSON object |
| `tag_paper(paper_id, tags)` | `Database.add_tag()` | Confirmation text |
| `get_stats()` | `Library.get_stats()` | JSON object |
| `ask_question(question, scope, auto_fetch)` | `Library.ask()` | JSON with answer+sources |
| `generate_review(topic, scope, auto_fetch)` | `Library.generate_review()` | Markdown review |
| `suggest_directions(topic)` | `Library.suggest_directions()` | Markdown report |
| `build_expertise(topic, question)` | `Library.build_expertise()` | Markdown report or answer |

## Adding a New Tool

1. Add the `@mcp.tool()` decorated async function in `mcp_server.py`
2. Use `_get_library()` to access Library
3. Return a string (JSON or text)
4. That's it — no registration needed, FastMCP auto-discovers

## Running the Server

```bash
# Via entry point
paper_expert-mcp

# Via Python module
python -m scholar.mcp_server

# Via direct script
python paper_expert/mcp_server.py
```

Transport: `stdio` (default for OpenCode/Claude Desktop)

## OpenCode Configuration

File: `opencode.json` in project root (or `~/.opencode/config.json`)

```json
{
  "mcpServers": {
    "paper_expert-agent": {
      "command": "python",
      "args": ["-m", "scholar.mcp_server"],
      "cwd": "D:\\opencode\\paper_expert-agent"
    }
  }
}
```

After adding/changing config, restart OpenCode for it to take effect.

## Library Singleton

`_get_library()` creates a single `Library` instance on first call and reuses it. This means:
- Config is loaded once at startup
- Database connection is reused
- PaperQA2 Docs are loaded once
- The singleton lives for the MCP server's lifetime

## Dual-Entry Coexistence

CLI and MCP share the same Library/Database/PaperQA stack:
- Both read from the same `config.toml`
- Both use the same `metadata.db` and `pdfs/` directory
- Papers added via MCP are visible in CLI and vice versa
- SQLite WAL mode handles concurrent access safely for single-user

Never duplicate business logic in `mcp_server.py` — always delegate to Library methods.
