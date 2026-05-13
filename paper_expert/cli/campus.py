"""CLI: paper_expert campus command -- campus proxy paper downloader."""

from __future__ import annotations

import asyncio

import typer
from rich.console import Console
from rich.table import Table

from paper_expert.cli import app
from paper_expert.core.config import PaperExpertConfig

console = Console()
campus_app = typer.Typer(
    name="campus",
    help="Campus network paper downloader for paywalled journals.",
    no_args_is_help=True,
)
app.add_typer(campus_app)


@campus_app.command("enable")
def campus_enable(
    proxy: str = typer.Option(
        ..., "--proxy", "-p",
        help="Campus proxy URL, e.g. http://proxy.campus.edu:8080",
    ),
) -> None:
    """Enable campus proxy for automatic paper downloads."""
    config = PaperExpertConfig.load()
    config.campus.enabled = True
    config.campus.http_proxy = proxy
    config.campus.https_proxy = proxy
    config.save()
    console.print(f"[green]Campus proxy enabled: {proxy}[/green]")


@campus_app.command("disable")
def campus_disable() -> None:
    """Disable campus proxy."""
    config = PaperExpertConfig.load()
    config.campus.enabled = False
    config.save()
    console.print("[yellow]Campus proxy disabled.[/yellow]")


@campus_app.command("config")
def campus_config() -> None:
    """Show campus proxy configuration."""
    config = PaperExpertConfig.load()
    c = config.campus
    table = Table(title="Campus Proxy Config")
    table.add_column("Key", style="bold")
    table.add_column("Value")
    table.add_row("enabled", str(c.enabled))
    table.add_row("http_proxy", c.http_proxy or "(not set)")
    table.add_row("https_proxy", c.https_proxy or "(not set)")
    table.add_row("ieee_inst_url", c.ieee_inst_url or "(not set)")
    table.add_row("acm_inst_url", c.acm_inst_url or "(not set)")
    console.print(table)


@campus_app.command("list-pending")
def list_pending(
    limit: int = typer.Option(50, "--limit", "-n", help="Max papers to show"),
) -> None:
    """List metadata-only papers that have DOIs (need PDF download)."""
    from paper_expert.core.library import Library

    config = PaperExpertConfig.load()
    lib = Library(config)

    papers = lib.list_papers(state="metadata-only", limit=limit)
    pending = [p for p in papers if p.doi]

    if not pending:
        console.print("[green]All papers have PDFs or no DOIs to download.[/green]")
        return

    table = Table(title=f"Pending Downloads ({len(pending)} papers)")
    table.add_column("ID", style="dim", width=4)
    table.add_column("Title", max_width=55)
    table.add_column("DOI", max_width=35)
    table.add_column("Year", width=5)

    for p in pending:
        table.add_row(
            str(p.id), p.title[:55], p.doi or "-", str(p.year or ""),
        )

    console.print(table)
    console.print("\nRun: paper-expert campus download-pending")


@campus_app.command("download-pending")
def download_pending(
    limit: int = typer.Option(10, "--limit", "-n", help="Max papers to download"),
) -> None:
    """Download PDFs for all metadata-only papers via campus proxy."""
    asyncio.run(_download_pending_async(limit))


async def _download_pending_async(limit: int) -> None:
    from paper_expert.core.library import Library

    config = PaperExpertConfig.load()
    if not config.campus.enabled:
        console.print(
            "[red]Campus proxy is not enabled.[/red]\n"
            "Run: paper-expert campus enable --proxy http://proxy.campus.edu:8080"
        )
        return

    lib = Library(config)
    papers = lib.list_papers(state="metadata-only", limit=limit * 3)
    pending = [p for p in papers if p.doi]
    if not pending:
        console.print("[green]No metadata-only papers with DOIs.[/green]")
        return


    from paper_expert.core.campus_downloader import campus_download

    success = 0
    skipped = 0
    failed = 0

    for i, p in enumerate(pending[:limit], 1):
        console.print(f"[{i}/{min(len(pending), limit)}] {p.title[:60]}...")
        pdf_dir = config.library_path / "pdfs" / "Campus"
        pdf_dir.mkdir(parents=True, exist_ok=True)
        safe_title = "".join(
            c if c.isalnum() or c in " -" else "_" for c in p.title
        )[:200].strip(" _-")
        dest = pdf_dir / f"{safe_title}.pdf"

        if dest.exists():
            skipped += 1
            console.print("  [dim]Already exists, upgrading to full-text...[/dim]")
            await lib.upgrade_to_fulltext(p.id, dest)
            continue

        ok = await campus_download(p.doi, dest, config)
        if ok:
            await lib.upgrade_to_fulltext(p.id, dest)
            success += 1
            console.print("  [green]Downloaded + upgraded[/green]")
        else:
            failed += 1
            console.print("  [yellow]Download failed (will retry later)[/yellow]")

        if success >= limit:
            break

    console.print(
        f"\n[bold]Done:[/bold] {success} downloaded, "
        f"{skipped} skipped, {failed} failed"
    )


@campus_app.command("export-dois")
def export_dois(
    output: str = typer.Option("pending_dois.txt", "--output", "-o", help="Output file"),
) -> None:
    """Export DOIs of metadata-only papers to a text file.

    Useful for downloading on another machine that has campus access.
    """
    from paper_expert.core.library import Library

    config = PaperExpertConfig.load()
    lib = Library(config)

    papers = lib.list_papers(state="metadata-only", limit=10000)
    dois = [p.doi for p in papers if p.doi]

    if not dois:
        console.print("[green]No pending DOIs.[/green]")
        return

    from pathlib import Path

    Path(output).write_text("\n".join(dois), encoding="utf-8")
    console.print(
        f"[green]Exported {len(dois)} DOIs to {output}[/green]\n"
        f"On campus machine, run: python campus_fetch.py {output} -o ./pdfs"
    )
