"""CLI: paper_expert config command."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from paper_expert.cli import app
from paper_expert.core.config import PaperExpertConfig

console = Console()
config_app = typer.Typer(name="config", help="Configuration management.", no_args_is_help=True)
app.add_typer(config_app)


@config_app.command()
def show() -> None:
    """Show current configuration."""
    config = PaperExpertConfig.load()

    table = Table(title="PaperExpert Configuration")
    table.add_column("Key", style="bold")
    table.add_column("Value")

    table.add_row("library_path", str(config.library_path))
    table.add_row("llm.local_model", config.llm.local_model)
    table.add_row("llm.cloud_model", config.llm.cloud_model)
    table.add_row("llm.embedding_model", config.llm.embedding_model)
    table.add_row("llm.api_base", config.llm.api_base or "[dim]not set (default OpenAI)[/dim]")
    table.add_row("api_keys.semantic_scholar", _mask(config.api_keys.semantic_scholar))
    table.add_row("api_keys.openai", _mask(config.api_keys.openai))
    table.add_row("api_keys.anthropic", _mask(config.api_keys.anthropic))
    table.add_row("api_keys.ieee_xplore", _mask(config.api_keys.ieee_xplore))
    table.add_row("api_keys.unpaywall_email", config.api_keys.unpaywall_email)
    table.add_row("search.default_sources", ", ".join(config.search.default_sources))
    table.add_row("search.default_limit", str(config.search.default_limit))
    table.add_row("parser.preferred", config.parser.preferred)
    table.add_row("parser.grobid_url", config.parser.grobid_url)
    table.add_row("parser.chunk_size", str(config.parser.chunk_size))
    table.add_row("parser.chunk_overlap", str(config.parser.chunk_overlap))
    table.add_row("notify.wechat_webhook", _mask(config.notify.wechat_webhook))
    table.add_row("notify.feishu_webhook", _mask(config.notify.feishu_webhook))
    table.add_row("notify.dingtalk_webhook", _mask(config.notify.dingtalk_webhook))
    table.add_row("campus.enabled", str(config.campus.enabled))
    if config.campus.enabled:
        table.add_row("campus.http_proxy", config.campus.http_proxy)
        table.add_row("campus.https_proxy", config.campus.https_proxy)
        table.add_row("campus.ieee_inst_url", config.campus.ieee_inst_url)
        table.add_row("campus.acm_inst_url", config.campus.acm_inst_url)

    console.print(table)


@config_app.command()
def set(
    key: str = typer.Argument(..., help="Config key (dotted, e.g. 'llm.local_model')"),
    value: str = typer.Argument(..., help="New value"),
) -> None:
    """Set a configuration value."""
    config = PaperExpertConfig.load()
    try:
        config.set_nested(key, value)
        config.save()
        console.print(f"[green]Set {key} = {value}[/green]")
    except KeyError as e:
        console.print(f"[red]{e}[/red]")


@config_app.command()
def reset() -> None:
    """Reset configuration to defaults."""
    config = PaperExpertConfig()
    config.save()
    console.print("[green]Configuration reset to defaults.[/green]")


def _mask(value: str) -> str:
    """Mask a secret value for display."""
    if not value:
        return "[dim]not set[/dim]"
    return value[:4] + "****" + value[-4:] if len(value) > 8 else "****"
