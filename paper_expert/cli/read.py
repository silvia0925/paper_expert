"""CLI: paper_expert read command."""

from __future__ import annotations

import asyncio

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from paper_expert.cli import app
from paper_expert.core.config import PaperExpertConfig
from paper_expert.core.library import Library

console = Console()


@app.command()
def read(
    paper_id: int = typer.Argument(..., help="Paper ID"),
    summary: bool = typer.Option(False, "--summary", help="Show AI-generated summary"),
    full: bool = typer.Option(False, "--full", help="Show full parsed text"),
    citations: bool = typer.Option(False, "--citations", "-c", help="Show citation relationships"),
) -> None:
    """View a paper's content, summary, or citations."""
    config = PaperExpertConfig.load()
    lib = Library(config)

    paper = lib.get_paper(paper_id)
    if not paper:
        console.print(f"[red]Paper {paper_id} not found.[/red]")
        return

    # Default: show paper info
    console.print(Panel(
        f"[bold]{paper.title}[/bold]\n\n"
        f"Authors: {', '.join(paper.authors) if paper.authors else 'Unknown'}\n"
        f"Year: {paper.year or 'Unknown'}  |  Venue: {paper.venue or 'Unknown'}\n"
        f"DOI: {paper.doi or 'N/A'}  |  arXiv: {paper.arxiv_id or 'N/A'}\n"
        f"State: {paper.state.value}  |  Citations: {paper.citation_count}\n"
        f"Tags: {', '.join(t.tag for t in paper.tags) if paper.tags else 'None'}",
        title=f"Paper #{paper.id}",
    ))

    if paper.abstract and not full:
        console.print(f"\n[bold]Abstract:[/bold]\n{paper.abstract}\n")

    if full:
        if paper.parsed_path:
            from pathlib import Path

            parsed = Path(paper.parsed_path)
            if parsed.exists():
                content = parsed.read_text(encoding="utf-8")
                console.print(f"\n[bold]Full Text:[/bold]\n{content}")
            else:
                console.print("[yellow]Parsed text file not found.[/yellow]")
        elif paper.state.value == "metadata-only":
            console.print("[yellow]This paper is metadata-only. Provide a PDF to enable full text.[/yellow]")
        else:
            console.print("[yellow]Full text not yet parsed.[/yellow]")

    if summary:
        asyncio.run(_show_summary(lib, paper_id))

    if citations:
        _show_citations(lib, paper_id)


def _show_citations(lib: Library, paper_id: int) -> None:
    """Display citation relationships for a paper."""
    from paper_expert.core.citations import discover_missing_papers, get_citation_summary

    summary = get_citation_summary(lib.db, paper_id)

    if summary["references"]:
        table = Table(title=f"References ({summary['reference_count']} papers this paper cites)")
        table.add_column("ID", style="dim", width=5)
        table.add_column("Title", max_width=55)
        table.add_column("Year", width=5)
        table.add_column("In Lib", width=6)

        for ref in summary["references"][:20]:
            in_lib = "[green]Y[/green]" if ref["in_library"] else "[dim]N[/dim]"
            table.add_row(str(ref["id"]), ref["title"][:55], str(ref.get("year", "")), in_lib)

        console.print(table)

    if summary["citations"]:
        table = Table(title=f"Cited By ({summary['citation_count']} papers cite this paper)")
        table.add_column("ID", style="dim", width=5)
        table.add_column("Title", max_width=55)
        table.add_column("Year", width=5)
        table.add_column("In Lib", width=6)

        for cit in summary["citations"][:20]:
            in_lib = "[green]Y[/green]" if cit["in_library"] else "[dim]N[/dim]"
            table.add_row(str(cit["id"]), cit["title"][:55], str(cit.get("year", "")), in_lib)

        console.print(table)

    missing = discover_missing_papers(lib.db, paper_id)
    if missing:
        console.print(
            f"\n[yellow]Found {len(missing)} related papers not fully in your library.[/yellow]"
        )
        console.print("Run [bold]paper_expert add <doi>[/bold] to add them.")


async def _show_summary(lib: Library, paper_id: int) -> None:
    """Generate or retrieve a paper summary."""
    config = lib.config
    if not config.api_keys.openai and not config.api_keys.anthropic:
        console.print(
            "[yellow]Summary generation requires a cloud LLM API key.[/yellow]\n"
            "Configure with: paper_expert config set api_keys.openai YOUR_KEY"
        )
        return

    with console.status("Generating summary..."):
        try:
            text = await lib.get_summary(paper_id)
        finally:
            await lib.close()

    if text:
        console.print(Panel(text, title="AI Summary", border_style="cyan"))
    else:
        console.print("[yellow]Could not generate summary for this paper.[/yellow]")
