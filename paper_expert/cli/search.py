"""CLI: paper_expert search command."""

from __future__ import annotations

import asyncio
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from paper_expert.cli import app
from paper_expert.core.config import PaperExpertConfig
from paper_expert.core.library import Library

console = Console()


@app.command()
def search(
    query: str = typer.Argument(..., help="Search query (keywords or natural language)"),
    source: Optional[str] = typer.Option(
        None, "--source", "-s", help="Source: semantic_scholar, openalex, arxiv, ieee"
    ),
    year: Optional[str] = typer.Option(
        None, "--year", "-y", help="Year filter, e.g. '2024' or '2023-2025'"
    ),
    limit: int = typer.Option(20, "--limit", "-n", help="Max results per source"),
    download: bool = typer.Option(False, "--download", "-d", help="Download results to library"),
) -> None:
    """Search for academic papers across multiple sources."""
    asyncio.run(_search_async(query, source, year, limit, download))


async def _search_async(
    query: str,
    source: str | None,
    year: str | None,
    limit: int,
    download: bool,
) -> None:
    config = PaperExpertConfig.load()
    lib = Library(config)

    try:
        sources = [source] if source else None
        with console.status("Searching..."):
            results = await lib.search(query, sources=sources, limit=limit, year=year)

        if not results:
            console.print("[yellow]No results found.[/yellow]")
            return

        table = Table(title=f"Search Results ({len(results)} papers)")
        table.add_column("#", style="dim", width=3)
        table.add_column("Title", max_width=60)
        table.add_column("Authors", max_width=30)
        table.add_column("Year", width=5)
        table.add_column("Cited", width=6, justify="right")
        table.add_column("PDF", width=4)
        table.add_column("In Lib", width=6)

        for i, r in enumerate(results, 1):
            first_author = r.authors[0] if r.authors else ""
            et_al = " et al." if len(r.authors) > 1 else ""
            pdf_status = "Y" if r.open_access_pdf_url else "N"
            lib_status = "[green]Y[/green]" if r.in_library else ""

            # Clean HTML tags and non-ASCII for Windows terminal safety
            import re
            clean_title = re.sub(r"<[^>]+>", "", r.title)
            clean_title = clean_title.encode("ascii", "replace").decode("ascii")

            table.add_row(
                str(i),
                clean_title[:60],
                f"{first_author}{et_al}",
                str(r.year or ""),
                str(r.citation_count),
                pdf_status,
                lib_status,
            )

        console.print(table)

        if download:
            console.print("\n[bold]Downloading papers to library...[/bold]")
            added = 0
            skipped = 0
            for r in results:
                if r.in_library:
                    skipped += 1
                    continue
                from paper_expert.models.paper import PaperMetadata

                metadata = PaperMetadata(
                    title=r.title,
                    authors=r.authors,
                    year=r.year,
                    venue=r.venue,
                    doi=r.doi,
                    arxiv_id=r.arxiv_id,
                    s2_paper_id=r.s2_paper_id,
                    citation_count=r.citation_count,
                    abstract=r.abstract,
                    open_access_pdf_url=r.open_access_pdf_url,
                    source=r.source,
                )
                paper = await lib.add_paper(metadata)
                if paper:
                    added += 1
            console.print(
                f"[green]Added {added} papers[/green], skipped {skipped} (already in library)"
            )
    finally:
        await lib.close()
