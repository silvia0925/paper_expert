"""CLI: paper_expert suggest command �?research direction suggestions."""

from __future__ import annotations

import asyncio

import typer
from rich.console import Console

from paper_expert.cli import app
from paper_expert.core.config import PaperExpertConfig
from paper_expert.core.library import Library

console = Console()


@app.command()
def suggest(
    topic: str = typer.Argument(..., help="Research topic to analyze"),
    trends: bool = typer.Option(True, "--trends/--no-trends", help="Include trend analysis"),
) -> None:
    """Analyze your knowledge base and suggest new research directions."""
    asyncio.run(_suggest_async(topic, trends))


async def _suggest_async(topic: str, trends: bool) -> None:
    config = PaperExpertConfig.load()
    if not config.api_keys.openai:
        console.print("[red]Direction analysis requires a cloud LLM API key.[/red]")
        return

    lib = Library(config)
    try:
        with console.status("Analyzing research landscape..."):
            report = await lib.suggest_directions(topic, include_trends=trends)

        console.print(report.full_text)
    finally:
        await lib.close()
