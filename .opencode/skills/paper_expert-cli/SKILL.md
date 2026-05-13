---
name: paper_expert-cli
description: "Load when adding new CLI commands, modifying command options, or debugging CLI behavior. Covers Typer patterns, command registration, async bridging, Rich output, and how to add a new command."
metadata:
  author: paper_expert-agent
  version: "1.0"
---

# Paper Expert CLI Development Guide

## Command Registration Pattern

```python
# paper_expert/cli/__init__.py creates the app
app = typer.Typer(name="scholar", ...)

# Each command file imports app and decorates:
# paper_expert/cli/search.py
from paper_expert.cli import app

@app.command()
def search(query: str = typer.Argument(...), ...):
    asyncio.run(_search_async(query, ...))

# Sub-command groups use add_typer:
# paper_expert/cli/lib.py
lib_app = typer.Typer(name="lib", ...)
app.add_typer(lib_app)

@lib_app.command(name="list")
def list_papers(...): ...
```

Registration happens in `cli/__init__.py` → `_register_commands()` imports all command modules.

## Async Bridging

All async work is bridged in each command function:
```python
@app.command()
def my_command(arg: str):
    """Sync entry point for Typer."""
    asyncio.run(_my_command_async(arg))

async def _my_command_async(arg: str):
    """Actual async implementation."""
    config = PaperExpertConfig.load()
    lib = Library(config)
    try:
        # ... async work with lib ...
    finally:
        await lib.close()
```

ALWAYS call `lib.close()` in finally block.

## Rich Output Conventions

- Tables: `rich.table.Table` for structured data
- Progress: `rich.progress.Progress` with `SpinnerColumn + BarColumn + MofNCompleteColumn`
- Status: `console.status("message...")` for single-task spinners
- Colors: `[green]...[/green]` for success, `[red]...[/red]` for errors, `[yellow]...[/yellow]` for warnings
- CRITICAL: No Unicode special chars (✓✗ etc.) — use ASCII (Y/N) for Windows GBK terminal safety
- HTML in titles: strip with `re.sub(r"<[^>]+>", "", title)` + `.encode("ascii","replace").decode("ascii")`

## Existing Commands

| Command | File | Type |
|---------|------|------|
| `scholar search <query>` | `search.py` | Top-level |
| `scholar add <identifier>` | `add.py` | Top-level |
| `scholar ask <question>` | `ask.py` | Top-level (Phase 2: QA + auto-fetch) |
| `scholar review <topic>` | `review.py` | Top-level (Phase 3: literature review) |
| `scholar suggest <topic>` | `suggest.py` | Top-level (Phase 3: direction suggestions) |
| `scholar expert <topic>` | `expert.py` | Top-level (Phase 3: domain expertise) |
| `scholar import <path>` | `import_cmd.py` | Top-level (note: file named `import_cmd.py` to avoid Python keyword) |
| `scholar read <paper_id>` | `read.py` | Top-level (--summary uses QA engine) |
| `scholar config show/set/reset` | `config.py` | Sub-group (`config_app`) |
| `scholar lib list/tag/classify/stats/vocab/export/rebuild-index/migrate-pdfs` | `lib.py` | Sub-group (`lib_app`) |

## How to Add a New Command

1. Create `paper_expert/cli/my_command.py`:
   ```python
   from paper_expert.cli import app
   
   @app.command()
   def my_command(...):
       asyncio.run(_my_command_async(...))
   ```

2. Register in `paper_expert/cli/__init__.py` → `_register_commands()`:
   ```python
   from paper_expert.cli import my_command  # noqa: F401
   ```

3. Follow the async bridging pattern above

## Global Options

Defined in `@app.callback()`:
- `--verbose / -v` (count): increases log verbosity (0=WARNING, 1=INFO, 2+=DEBUG)
- `--quiet / -q`: suppresses non-error output

These set up logging via `scholar.core.logging.setup_logging()`.
