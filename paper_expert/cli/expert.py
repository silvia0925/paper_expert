"""CLI: paper_expert expert command �?domain expertise building."""

from __future__ import annotations

import asyncio
from typing import Optional

import typer
from rich.console import Console

from paper_expert.cli import app
from paper_expert.core.config import PaperExpertConfig
from paper_expert.core.library import Library

console = Console()


@app.command()
def expert(
    topic: str = typer.Argument(..., help="Domain/topic to build expertise on"),
    update: bool = typer.Option(False, "--update", "-u", help="Update existing expertise with new papers"),
    ask: Optional[str] = typer.Option(None, "--ask", "-a", help="Ask an expert-level question about this domain"),
    verbose: bool = typer.Option(False, "--verbose", "-V", help="Show digestion progress"),
) -> None:
    """Build domain expertise by systematically reading papers on a topic."""
    asyncio.run(_expert_async(topic, update, ask, verbose))


async def _expert_async(topic: str, update: bool, ask: str | None, verbose: bool) -> None:
    config = PaperExpertConfig.load()
    if not config.api_keys.openai:
        console.print("[red]Domain expertise requires a cloud LLM API key.[/red]")
        return

    lib = Library(config)

    def _progress(msg: str) -> None:
        if verbose:
            console.print(f"  [dim]{msg}[/dim]")

    try:
        if ask:
            with console.status("Consulting domain knowledge..."):
                answer = await lib.build_expertise(topic, ask=ask)
            console.print(answer)
        else:
            with console.status("Building expertise...") if not verbose else _nullcontext():
                report = await lib.build_expertise(
                    topic, update=update, on_progress=_progress,
                )
            console.print(report)
    finally:
        await lib.close()


class _nullcontext:
    def __enter__(self) -> None:
        return None
    def __exit__(self, *args: object) -> None:
        pass
