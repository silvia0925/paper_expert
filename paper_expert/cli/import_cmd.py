"""CLI: paper_expert import command."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer
from rich.console import Console
from rich.progress import BarColumn, MofNCompleteColumn, Progress, SpinnerColumn, TextColumn

from paper_expert.cli import app
from paper_expert.core.config import PaperExpertConfig
from paper_expert.core.library import Library

console = Console()


@app.command(name="import")
def import_cmd(
    path: Path = typer.Argument(..., help="Path to .bib file, directory, or Zotero data dir"),
    zotero: bool = typer.Option(False, "--zotero", help="Import from Zotero data directory"),
    recursive: bool = typer.Option(True, "--recursive/--no-recursive", help="Scan subdirectories"),
) -> None:
    """Import papers from BibTeX, local directory, or Zotero."""
    asyncio.run(_import_async(path, zotero, recursive))


async def _import_async(path: Path, zotero: bool, recursive: bool) -> None:
    config = PaperExpertConfig.load()
    lib = Library(config)

    try:
        if zotero:
            await _import_zotero(lib, path)
            return

        if path.suffix.lower() == ".bib":
            await _import_bibtex(lib, path)
            return

        if path.is_dir():
            await _import_directory(lib, path, recursive)
            return

        console.print(f"[red]Don't know how to import: {path}[/red]")
        console.print("Provide a .bib file, a directory of PDFs, or use --zotero")
    finally:
        await lib.close()


async def _import_zotero(lib: Library, zotero_dir: Path) -> None:
    """Import from Zotero data directory."""
    from paper_expert.importers.zotero import read_zotero_library, to_metadata_list

    console.print(f"[bold]Importing from Zotero:[/bold] {zotero_dir}")

    try:
        items = read_zotero_library(zotero_dir)
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        return

    metadata_list = to_metadata_list(items)
    added, skipped, failed = 0, 0, 0

    with Progress(
        SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
        BarColumn(), MofNCompleteColumn(), console=console,
    ) as progress:
        task = progress.add_task("Importing...", total=len(metadata_list))

        for metadata, pdf_path in metadata_list:
            if lib.db.paper_exists(doi=metadata.doi, title=metadata.title):
                skipped += 1
                progress.advance(task)
                continue
            try:
                # Preserve Zotero tags as L2
                paper = await lib.add_paper(metadata, pdf_path=pdf_path)
                if paper:
                    zotero_item = next(
                        (i for i in items if i["title"] == metadata.title), None
                    )
                    if zotero_item and zotero_item.get("tags"):
                        for tag in zotero_item["tags"]:
                            lib.db.add_tag(paper.id, "L2", tag)
                    added += 1
                else:
                    failed += 1
            except Exception:
                failed += 1
            progress.advance(task)

    console.print(
        f"\n[green]Done:[/green] {added} added, {skipped} skipped, {failed} failed"
    )


async def _import_bibtex(lib: Library, bib_path: Path) -> None:
    """Import from BibTeX file."""
    from paper_expert.importers.bibtex import parse_bibtex

    console.print(f"[bold]Importing BibTeX:[/bold] {bib_path}")

    entries = parse_bibtex(bib_path)
    added, skipped, failed = 0, 0, 0

    with Progress(
        SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
        BarColumn(), MofNCompleteColumn(), console=console,
    ) as progress:
        task = progress.add_task("Importing...", total=len(entries))

        for metadata in entries:
            if lib.db.paper_exists(doi=metadata.doi, title=metadata.title):
                skipped += 1
                progress.advance(task)
                continue
            try:
                paper = await lib.add_paper(metadata)
                if paper:
                    added += 1
                else:
                    failed += 1
            except Exception:
                failed += 1
            progress.advance(task)

    console.print(
        f"\n[green]Done:[/green] {added} added, {skipped} skipped, {failed} failed"
    )


async def _import_directory(lib: Library, directory: Path, recursive: bool) -> None:
    """Import PDFs from a local directory."""
    from paper_expert.importers.directory import pdf_to_metadata, scan_pdfs

    console.print(f"[bold]Importing PDFs from:[/bold] {directory}")

    pdfs = scan_pdfs(directory, recursive=recursive)
    if not pdfs:
        console.print("[yellow]No PDF files found.[/yellow]")
        return

    added, skipped, failed = 0, 0, 0

    with Progress(
        SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
        BarColumn(), MofNCompleteColumn(), console=console,
    ) as progress:
        task = progress.add_task("Importing...", total=len(pdfs))

        for pdf_path in pdfs:
            try:
                metadata = pdf_to_metadata(pdf_path)
                paper = await lib.add_paper(metadata, pdf_path=pdf_path)
                if paper:
                    added += 1
                else:
                    failed += 1
            except Exception:
                failed += 1
            progress.advance(task)

    console.print(
        f"\n[green]Done:[/green] {added} added, {skipped} skipped, {failed} failed"
    )
