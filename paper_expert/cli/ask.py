"""CLI: paper_expert ask command �?question answering over the knowledge base."""

from __future__ import annotations

import asyncio
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel

from paper_expert.cli import app
from paper_expert.core.config import PaperExpertConfig
from paper_expert.core.library import Library

console = Console()


@app.command()
def ask(
    question: str = typer.Argument(..., help="Research question to answer"),
    scope: Optional[str] = typer.Option(
        None, "--scope", "-s", help="Scope filter: 'tag:OPC', 'year:2024-2025'"
    ),
    auto_fetch: bool = typer.Option(
        False, "--auto-fetch", "-f", help="Automatically fetch new papers if answer is insufficient"
    ),
    fetch_limit: int = typer.Option(
        5, "--fetch-limit", help="Max papers to fetch per auto-fetch iteration"
    ),
) -> None:
    """Ask a question based on papers in your knowledge base."""
    asyncio.run(_ask_async(question, scope, auto_fetch, fetch_limit))


async def _ask_async(
    question: str,
    scope: str | None,
    auto_fetch: bool,
    fetch_limit: int,
) -> None:
    config = PaperExpertConfig.load()

    # Validate cloud LLM is configured
    if not config.api_keys.openai and not config.api_keys.anthropic:
        console.print(
            "[red]QA requires a cloud LLM API key.[/red]\n"
            "Configure with:\n"
            "  paper_expert config set api_keys.openai YOUR_KEY\n"
            "  or\n"
            "  paper_expert config set api_keys.anthropic YOUR_KEY"
        )
        return

    lib = Library(config)

    def _progress_callback(progress: object) -> None:
        msg = getattr(progress, "message", "")
        iteration = getattr(progress, "iteration", 0)
        if msg:
            console.print(f"  [dim][{iteration}][/dim] {msg}")

    try:
        with console.status("Thinking...") if not auto_fetch else _nullcontext():
            answer = await lib.ask(
                question=question,
                scope=scope,
                auto_fetch=auto_fetch,
                fetch_limit=fetch_limit,
                on_progress=_progress_callback if auto_fetch else None,
            )

        if answer.error:
            console.print(f"[red]Error:[/red] {answer.error}")
            return

        # Display confidence
        conf_style = {
            "high": "[green]HIGH[/green]",
            "medium": "[yellow]MEDIUM[/yellow]",
            "low": "[red]LOW[/red]",
        }
        conf_display = conf_style.get(answer.confidence.value, answer.confidence.value)

        console.print(Panel(
            answer.answer,
            title=f"Answer (confidence: {conf_display})",
            border_style="green" if answer.is_sufficient else "yellow",
        ))

        # Display sources
        if answer.sources:
            console.print(f"\n[bold]Sources ({len(answer.sources)} passages):[/bold]")
            console.print(answer.format_sources())

        # Display cost
        if answer.cost > 0:
            console.print(f"[dim]Cost: ${answer.cost:.4f}[/dim]")

        if not answer.is_sufficient and not auto_fetch:
            console.print(
                "\n[yellow]Answer may be incomplete. "
                "Try --auto-fetch to search for additional papers.[/yellow]"
            )

    finally:
        await lib.close()


class _nullcontext:
    """Minimal no-op context manager for Python 3.10 compat."""

    def __enter__(self) -> None:
        return None

    def __exit__(self, *args: object) -> None:
        pass
