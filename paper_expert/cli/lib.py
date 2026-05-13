"""CLI: paper_expert lib command group (list, tag, classify, stats, vocab, export)."""

from __future__ import annotations

import asyncio
import csv
import io
import json
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from paper_expert.cli import app
from paper_expert.core.config import PaperExpertConfig
from paper_expert.core.library import Library

console = Console()
lib_app = typer.Typer(name="lib", help="Knowledge base management commands.", no_args_is_help=True)
app.add_typer(lib_app)


@lib_app.command(name="list")
def list_papers(
    tag: Optional[str] = typer.Option(None, "--tag", "-t", help="Filter by tag"),
    year: Optional[int] = typer.Option(None, "--year", "-y", help="Filter by year"),
    state: Optional[str] = typer.Option(None, "--state", help="Filter: full-text, metadata-only"),
    sort: str = typer.Option("date_added", "--sort", "-s", help="Sort: date_added, year, citation_count, title"),
    limit: int = typer.Option(20, "--limit", "-n", help="Max results"),
) -> None:
    """List papers in the knowledge base with optional filters."""
    config = PaperExpertConfig.load()
    lib = Library(config)

    papers = lib.list_papers(state=state, year=year, tag=tag, sort_by=sort, limit=limit)

    if not papers:
        console.print("[yellow]No papers found.[/yellow]")
        return

    table = Table(title=f"Library ({len(papers)} papers)")
    table.add_column("ID", style="dim", width=5)
    table.add_column("Title", max_width=55)
    table.add_column("Year", width=5)
    table.add_column("Cited", width=6, justify="right")
    table.add_column("State", width=14)
    table.add_column("Tags", max_width=30)

    for p in papers:
        tags_str = ", ".join(t.tag for t in p.tags[:5])
        state_style = "[green]full-text[/green]" if p.state.value == "full-text" else "[dim]metadata-only[/dim]"
        table.add_row(
            str(p.id), p.title[:55], str(p.year or ""),
            str(p.citation_count), state_style, tags_str,
        )

    console.print(table)


@lib_app.command()
def tag(
    paper_id: int = typer.Argument(..., help="Paper ID"),
    add: Optional[list[str]] = typer.Option(None, "--add", "-a", help="Add tags"),
    remove: Optional[list[str]] = typer.Option(None, "--remove", "-r", help="Remove tags"),
) -> None:
    """Add or remove tags on a paper."""
    config = PaperExpertConfig.load()
    lib = Library(config)

    paper = lib.get_paper(paper_id)
    if not paper:
        console.print(f"[red]Paper {paper_id} not found.[/red]")
        return

    if add:
        for t in add:
            lib.db.add_tag(paper_id, "L2", t)
            console.print(f"[green]+[/green] {t}")

    if remove:
        for t in remove:
            lib.db.remove_tag(paper_id, t)
            console.print(f"[red]-[/red] {t}")

    # Show current tags
    tags = lib.db.get_tags(paper_id)
    if tags:
        tag_str = ", ".join(f"[{t['level']}]{t['tag']}" for t in tags)
        console.print(f"\nCurrent tags: {tag_str}")


@lib_app.command()
def classify(
    untagged: bool = typer.Option(True, "--untagged/--all", help="Only classify untagged papers"),
) -> None:
    """Run LLM auto-classification on papers."""
    asyncio.run(_classify_async(untagged))


async def _classify_async(untagged: bool) -> None:
    from paper_expert.core.classifier import batch_classify

    config = PaperExpertConfig.load()
    lib = Library(config)

    model = config.llm.local_model.replace("ollama/", "")
    with console.status(f"Classifying with {model}..."):
        count = await batch_classify(lib.db, ollama_model=model)

    console.print(f"[green]Classified {count} papers.[/green]")

    # Check for suggested tags ready for promotion
    from paper_expert.core.vocabulary import check_suggested_tags

    suggestions = check_suggested_tags(lib.db)
    if suggestions:
        console.print("\n[bold]Suggested tags ready for vocabulary:[/bold]")
        for s in suggestions:
            console.print(f"  '{s['tag']}' ({s['count']} papers)")


@lib_app.command()
def stats() -> None:
    """Show knowledge base statistics."""
    config = PaperExpertConfig.load()
    lib = Library(config)

    s = lib.get_stats()
    console.print("\n[bold]Knowledge Base Statistics[/bold]\n")
    console.print(f"  Total papers: {s['total']}")
    console.print(f"  Storage: {s['storage_mb']} MB\n")

    if s["by_state"]:
        console.print("  [bold]By State:[/bold]")
        for state, count in s["by_state"].items():
            console.print(f"    {state}: {count}")

    # PDF status summary
    pdf = s.get("pdf_status", {})
    if pdf:
        console.print("\n  [bold]PDF Status:[/bold]")
        console.print(f"    Has PDF: {pdf.get('has_pdf', 0)}")
        console.print(f"    Has parsed text: {pdf.get('has_parsed_text', 0)}")
        meta_only = pdf.get('metadata_only', 0)
        if meta_only > 0:
            console.print(f"    [yellow]Metadata-only (no PDF): {meta_only}[/yellow]")
        unparsed = pdf.get('pdf_but_unparsed', 0)
        if unparsed > 0:
            console.print(f"    [yellow]Has PDF but not parsed: {unparsed}[/yellow]")
            console.print("    [dim]Run 'paper-expert lib rebuild-index' to parse them.[/dim]")

    if s["by_category"]:
        console.print("\n  [bold]By Category (L0):[/bold]")
        for cat, count in s["by_category"].items():
            console.print(f"    {cat}: {count}")

    if s["by_year"]:
        console.print("\n  [bold]By Year (top 10):[/bold]")
        for year, count in s["by_year"].items():
            console.print(f"    {year}: {count}")


@lib_app.command()
def vocab(
    add_entry: Optional[str] = typer.Option(None, "--add", help="Add vocabulary entry (canonical term)"),
    aliases: Optional[str] = typer.Option(None, "--aliases", help="Comma-separated aliases for --add"),
    remove_entry: Optional[str] = typer.Option(None, "--remove", help="Remove vocabulary entry"),
    init: bool = typer.Option(False, "--init", help="Initialize vocabulary with defaults"),
) -> None:
    """Manage the controlled vocabulary for L1 classification."""
    config = PaperExpertConfig.load()
    db_path = config.library_path / "metadata.db"
    from paper_expert.core.database import Database

    db = Database(db_path)

    if init:
        from paper_expert.core.vocabulary import init_vocabulary

        count = init_vocabulary(db)
        console.print(f"[green]Initialized vocabulary with {count} entries.[/green]")
        return

    if add_entry:
        alias_list = [a.strip() for a in (aliases or "").split(",") if a.strip()]
        db.add_vocabulary(add_entry, alias_list)
        console.print(f"[green]Added:[/green] {add_entry} (aliases: {alias_list})")
        return

    if remove_entry:
        db.remove_vocabulary(remove_entry)
        console.print(f"[red]Removed:[/red] {remove_entry}")
        return

    # Default: list vocabulary
    entries = db.get_vocabulary()
    if not entries:
        console.print("[yellow]No vocabulary entries. Run with --init to set up defaults.[/yellow]")
        return

    table = Table(title="Controlled Vocabulary")
    table.add_column("Canonical", style="bold")
    table.add_column("Aliases")

    for entry in entries:
        aliases_list = json.loads(entry["aliases_json"])
        table.add_row(entry["canonical"], ", ".join(aliases_list))

    console.print(table)


@lib_app.command()
def export(
    format: str = typer.Option("bibtex", "--format", "-f", help="Export format: bibtex, csv"),
    tag: Optional[str] = typer.Option(None, "--tag", "-t", help="Filter by tag"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Output file (default: stdout)"),
) -> None:
    """Export papers from the knowledge base."""
    config = PaperExpertConfig.load()
    lib = Library(config)

    papers = lib.list_papers(tag=tag, limit=10000)

    if format == "bibtex":
        content = _export_bibtex(papers)
    elif format == "csv":
        content = _export_csv(papers)
    else:
        console.print(f"[red]Unknown format: {format}[/red]")
        return

    if output:
        from pathlib import Path

        Path(output).write_text(content, encoding="utf-8")
        console.print(f"[green]Exported {len(papers)} papers to {output}[/green]")
    else:
        console.print(content)


@lib_app.command(name="rebuild-index")
def rebuild_index() -> None:
    """Rebuild the PaperQA2 vector index from stored PDFs."""
    asyncio.run(_rebuild_async())


async def _rebuild_async() -> None:
    from pathlib import Path

    config = PaperExpertConfig.load()
    lib = Library(config)

    papers = lib.list_papers(state="full-text", limit=100000)
    pdf_paths = [Path(p.pdf_path) for p in papers if p.pdf_path]

    with console.status(f"Rebuilding index from {len(pdf_paths)} PDFs..."):
        count = await lib.paperqa.rebuild_index(pdf_paths)

    console.print(f"[green]Rebuilt index: {count}/{len(pdf_paths)} documents.[/green]")


@lib_app.command(name="migrate-pdfs")
def migrate_pdfs() -> None:
    """Move flat PDFs from pdfs/ root into category subfolders.

    Reads each paper's L0 tag from the database and moves its PDF
    into the corresponding pdfs/<category>/ subfolder.
    """
    from pathlib import Path

    from paper_expert.core.classifier import classify_l0

    config = PaperExpertConfig.load()
    lib = Library(config)
    pdf_dir = config.library_path / "pdfs"

    papers = lib.list_papers(limit=100000)
    moved = 0
    skipped = 0

    for p in papers:
        if not p.pdf_path:
            continue

        pdf_path = Path(p.pdf_path)
        if not pdf_path.exists():
            continue

        # Skip if already in a subfolder
        if pdf_path.parent != pdf_dir:
            skipped += 1
            continue

        # Determine category from existing L0 tags or re-classify
        l0_tags = [t.tag for t in p.tags if t.level.value == "L0"]
        if not l0_tags:
            l0_tags = classify_l0(p.title, p.abstract)
        category = l0_tags[0] if l0_tags else "Uncategorized"

        # Sanitize category name
        safe_cat = "".join(
            c if c.isalnum() or c in " -_" else "_"
            for c in category
        ).strip()
        target_dir = pdf_dir / safe_cat
        target_dir.mkdir(parents=True, exist_ok=True)

        # Build new filename from title
        safe_title = "".join(
            c if c.isalnum() or c in " -" else "_"
            for c in p.title
        ).strip()
        while "  " in safe_title:
            safe_title = safe_title.replace("  ", " ")
        while "__" in safe_title:
            safe_title = safe_title.replace("__", "_")
        safe_title = safe_title[:200].strip(" _-")
        new_path = target_dir / f"{safe_title}.pdf"

        # Move file
        try:
            pdf_path.rename(new_path)
            lib.db.update_paper(p.id, pdf_path=str(new_path))
            console.print(f"  [green]Moved:[/green] {pdf_path.name} -> {safe_cat}/{new_path.name}")
            moved += 1
        except OSError as e:
            console.print(f"  [red]Failed:[/red] {pdf_path.name}: {e}")

    console.print(f"\n[green]Done:[/green] {moved} moved, {skipped} already in subfolders")


def _export_bibtex(papers: list) -> str:
    """Generate BibTeX string from papers."""
    lines: list[str] = []
    for p in papers:
        key = p.doi or p.arxiv_id or f"paper{p.id}"
        key = key.replace("/", "_").replace(".", "_")
        lines.append(f"@article{{{key},")
        lines.append(f'  title = {{{p.title}}},')
        if p.authors:
            authors_str = " and ".join(p.authors)
            lines.append(f"  author = {{{authors_str}}},")
        if p.year:
            lines.append(f"  year = {{{p.year}}},")
        if p.venue:
            lines.append(f"  journal = {{{p.venue}}},")
        if p.doi:
            lines.append(f"  doi = {{{p.doi}}},")
        if p.arxiv_id:
            lines.append(f"  eprint = {{{p.arxiv_id}}},")
            lines.append("  archiveprefix = {arXiv},")
        lines.append("}")
        lines.append("")
    return "\n".join(lines)


def _export_csv(papers: list) -> str:
    """Generate CSV string from papers."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["DOI", "Title", "Authors", "Year", "Venue", "Tags", "State", "Citations"])
    for p in papers:
        tags = "; ".join(t.tag for t in p.tags)
        authors = "; ".join(p.authors)
        writer.writerow([p.doi, p.title, authors, p.year, p.venue, tags, p.state.value, p.citation_count])
    return output.getvalue()
