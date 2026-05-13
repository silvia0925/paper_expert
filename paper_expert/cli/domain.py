"""CLI: paper_expert domain command -- research domain setup and management."""

from __future__ import annotations

import json

import typer
from rich.console import Console
from rich.table import Table

from paper_expert.core.config import PaperExpertConfig
from paper_expert.core.domain import init_domain

console = Console()
domain_app = typer.Typer(name="domain", help="Research domain configuration.")


@domain_app.command("init")
def domain_init(
    name: str = typer.Argument(help="Your research field name, e.g. 'Quantum Computing'"),
    keywords: str = typer.Option("", "--keywords", "-k",
                                  help="L0 keyword groups as JSON, e.g. '{\"Physics\": [\"quantum\", \"qubit\"]}'"),
) -> None:
    """Initialize your research domain for paper classification."""
    config = PaperExpertConfig.load()

    l0_keywords: dict[str, list[str]] = {}
    if keywords:
        try:
            l0_keywords = json.loads(keywords)
        except json.JSONDecodeError:
            console.print("[red]Invalid JSON format for --keywords[/red]")
            raise typer.Exit(1)

    domain = init_domain(name, l0_keywords=l0_keywords)
    config.domain = domain
    config.save()

    console.print(f"[green]Domain initialized: {name}[/green]")
    if l0_keywords:
        table = Table(title="L0 Keyword Groups")
        table.add_column("Group")
        table.add_column("Keywords", style="cyan")
        for group, kws in l0_keywords.items():
            table.add_row(group, ", ".join(kws))
        console.print(table)
    else:
        console.print("[yellow]No L0 keywords defined. Add them with 'domain add-keyword'.[/yellow]")


@domain_app.command("show")
def domain_show() -> None:
    """Display current domain configuration."""
    config = PaperExpertConfig.load()
    domain = config.domain

    if not domain.is_initialized():
        console.print("[yellow]No domain configured. Run 'domain init <name>' first.[/yellow]")
        raise typer.Exit(0)

    console.print(f"[bold]Domain: {domain.domain_name}[/bold]\n")

    if domain.l0_keywords:
        table = Table(title="L0 Keyword Groups")
        table.add_column("Group")
        table.add_column("Keywords", style="cyan")
        table.add_column("Count", style="green")
        for group, kws in domain.l0_keywords.items():
            table.add_row(group, ", ".join(kws), str(len(kws)))
        console.print(table)

    if domain.l1_vocabulary:
        table = Table(title="L1 Vocabulary")
        table.add_column("Canonical")
        table.add_column("Aliases", style="cyan")
        for canonical, aliases in domain.l1_vocabulary.items():
            table.add_row(canonical, ", ".join(aliases))
        console.print(table)

    if not domain.l0_keywords and not domain.l1_vocabulary:
        console.print("[yellow]Domain is initialized but has no keywords or vocabulary.[/yellow]")


@domain_app.command("add-keyword")
def domain_add_keyword(
    group: str = typer.Argument(help="Domain group name, e.g. 'Physics'"),
    keyword: str = typer.Argument(help="Keyword to add, e.g. 'quantum'"),
) -> None:
    """Add a keyword to an L0 domain group."""
    config = PaperExpertConfig.load()
    domain = config.domain

    if not domain.is_initialized():
        console.print("[yellow]No domain configured. Run 'domain init <name>' first.[/yellow]")
        raise typer.Exit(1)

    if group not in domain.l0_keywords:
        domain.l0_keywords[group] = []

    if keyword not in domain.l0_keywords[group]:
        domain.l0_keywords[group].append(keyword)
        config.save()
        console.print(f"[green]Added '{keyword}' to group '{group}'[/green]")
    else:
        console.print(f"[yellow]'{keyword}' already in group '{group}'[/yellow]")


@domain_app.command("add-vocab")
def domain_add_vocab(
    canonical: str = typer.Argument(help="Canonical term, e.g. 'GAN'"),
    aliases: str = typer.Argument(help="Comma-separated aliases, e.g. 'Generative Adversarial Network, GANs'"),
) -> None:
    """Add a vocabulary entry for L1 tag normalization."""
    config = PaperExpertConfig.load()
    domain = config.domain

    if not domain.is_initialized():
        console.print("[yellow]No domain configured. Run 'domain init <name>' first.[/yellow]")
        raise typer.Exit(1)

    alias_list = [a.strip() for a in aliases.split(",") if a.strip()]
    domain.l1_vocabulary[canonical] = alias_list
    config.save()

    console.print(f"[green]Added vocab: {canonical} -> {', '.join(alias_list)}[/green]")
