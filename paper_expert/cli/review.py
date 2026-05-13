"""CLI: paper_expert review command �?generate literature reviews."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from paper_expert.cli import app
from paper_expert.core.config import PaperExpertConfig
from paper_expert.core.library import Library

console = Console()


@app.command()
def review(
    topic: str = typer.Argument(..., help="Research topic for the review"),
    scope: Optional[str] = typer.Option(None, "--scope", "-s", help="Scope filter: 'tag:OPC', 'year:2024-2025'"),
    auto_fetch: bool = typer.Option(False, "--auto-fetch", "-f", help="Fetch more papers if coverage is thin"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Save review to file"),
    refresh: bool = typer.Option(False, "--refresh", help="Re-generate even if cached"),
    verbose: bool = typer.Option(False, "--verbose", "-V", help="Show pipeline stage progress"),
) -> None:
    """Generate a structured literature review for a topic."""
    asyncio.run(_review_async(topic, scope, auto_fetch, output, refresh, verbose))


async def _review_async(
    topic: str, scope: str | None, auto_fetch: bool,
    output: str | None, refresh: bool, verbose: bool,
) -> None:
    config = PaperExpertConfig.load()
    if not config.api_keys.openai:
        console.print("[red]Review generation requires a cloud LLM API key.[/red]")
        console.print("Configure with: paper_expert config set api_keys.openai YOUR_KEY")
        return

    lib = Library(config)

    def _progress(msg: str) -> None:
        if verbose:
            console.print(f"  [dim]{msg}[/dim]")

    try:
        with console.status("Generating review...") if not verbose else _nullcontext():
            review_text = await lib.generate_review(
                topic=topic, scope=scope, auto_fetch=auto_fetch,
                refresh=refresh, on_progress=_progress,
            )

        if output:
            Path(output).write_text(review_text, encoding="utf-8")
            console.print(f"[green]Review saved to {output}[/green]")
        else:
            console.print(review_text)
    finally:
        await lib.close()


class _nullcontext:
    def __enter__(self) -> None:
        return None
    def __exit__(self, *args: object) -> None:
        pass
