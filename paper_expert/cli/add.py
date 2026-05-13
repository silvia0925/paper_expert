"""CLI: paper_expert add command."""

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
def add(
    identifier: str = typer.Argument(
        ..., help="Paper identifier: arxiv:<id>, doi:<doi>, s2:<id>, or path to PDF"
    ),
    pdf: Optional[Path] = typer.Option(
        None, "--pdf", help="Associate a local PDF with this paper"
    ),
) -> None:
    """Add a single paper to the knowledge base."""
    asyncio.run(_add_async(identifier, pdf))


async def _add_async(identifier: str, pdf_path: Path | None) -> None:
    config = PaperExpertConfig.load()
    lib = Library(config)

    try:
        # Check if identifier is a local PDF path
        local_path = Path(identifier)
        if local_path.exists() and local_path.suffix.lower() == ".pdf":
            console.print(f"Importing local PDF: {local_path.name}")
            from paper_expert.importers.directory import pdf_to_metadata

            metadata = pdf_to_metadata(local_path)
            paper = await lib.add_paper(metadata, pdf_path=local_path)
        else:
            with console.status(f"Resolving: {identifier}"):
                paper = await lib.add_by_identifier(identifier, pdf_path=pdf_path)

        if paper:
            state_label = "[PDF]" if paper.state.value == "full-text" else "[meta]"
            console.print(
                f"\n{state_label} [green]Added:[/green] {paper.title}"
            )
            console.print(f"   State: {paper.state.value}")
            if paper.tags:
                tag_str = ", ".join(t.tag for t in paper.tags)
                console.print(f"   Tags: {tag_str}")
        else:
            console.print("[red]Failed to add paper.[/red]")
    finally:
        await lib.close()
