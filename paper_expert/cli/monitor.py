"""CLI: paper_expert monitor command -- periodic paper research watch."""

from __future__ import annotations

import asyncio
import json

import typer
from rich.console import Console
from rich.table import Table

from paper_expert.cli import app
from paper_expert.core.config import PaperExpertConfig
from paper_expert.core.library import Library

console = Console()
monitor_app = typer.Typer(
    name="monitor",
    help="Research topic monitoring -- watch keywords and get notified of new papers.",
    no_args_is_help=True,
)
app.add_typer(monitor_app)

_Q_HELP = "Search queries as JSON array. Example: '[\"quantum error\"]'"
_S_HELP = "Sources as JSON array. Example: '[\"semantic_scholar\"]'. Default: config"
_C_HELP = "Notify channels as JSON array. Example: '[\"wechat\",\"feishu\"]'. Default: all"


@monitor_app.command("add-watch")
def add_watch(
    name: str = typer.Argument(help="Watch topic name"),
    queries: str = typer.Option(..., "--queries", "-q", help=_Q_HELP),
    sources: str = typer.Option("", "--sources", "-s", help=_S_HELP),
    limit: int = typer.Option(10, "--limit", "-n", help="Max papers per query"),
    channels: str = typer.Option("", "--channels", "-c", help=_C_HELP),
) -> None:
    """Add a research direction to watch for new papers."""
    config = PaperExpertConfig.load()
    lib = Library(config)

    try:
        query_list = json.loads(queries)
        if not isinstance(query_list, list) or not query_list:
            console.print("[red]--queries must be a non-empty JSON array[/red]")
            raise typer.Exit(1)
    except json.JSONDecodeError:
        console.print("[red]Invalid JSON for --queries[/red]")
        raise typer.Exit(1)

    source_list: list[str] | None = None
    if sources:
        try:
            source_list = json.loads(sources)
        except json.JSONDecodeError:
            console.print("[red]Invalid JSON for --sources[/red]")
            raise typer.Exit(1)

    channel_list: list[str] | None = None
    if channels:
        try:
            channel_list = json.loads(channels)
        except json.JSONDecodeError:
            console.print("[red]Invalid JSON for --channels[/red]")
            raise typer.Exit(1)

    topic_id = lib.add_watch_topic(
        name=name,
        queries=query_list,
        sources=source_list,
        fetch_limit=limit,
        notify_channels=channel_list,
    )
    console.print(f"[green]Added watch topic #{topic_id}: {name}[/green]")


@monitor_app.command("list-watches")
def list_watches() -> None:
    """List all configured watch topics."""
    config = PaperExpertConfig.load()
    lib = Library(config)

    topics = lib.list_watch_topics()
    if not topics:
        console.print("[yellow]No watch topics configured.[/yellow]")
        return

    table = Table(title="Watch Topics")
    table.add_column("ID", style="dim", width=4)
    table.add_column("Name", max_width=30)
    table.add_column("Queries", max_width=40)
    table.add_column("Active", width=6)
    table.add_column("Notify", max_width=20)
    table.add_column("Last Run", max_width=20)

    for t in topics:
        active = "[green]yes[/green]" if t["is_active"] else "[dim]no[/dim]"
        channels = ", ".join(t.get("notify_channels", [])) or "all"
        last_run = t.get("last_run_at", "") or "-"
        if len(last_run) > 16:
            last_run = last_run[:16]
        table.add_row(
            str(t["id"]),
            t["name"],
            ", ".join(t.get("queries", []))[:40],
            active,
            channels,
            last_run,
        )
    console.print(table)


@monitor_app.command("remove-watch")
def remove_watch(
    watch_id: int = typer.Argument(help="Watch topic ID to remove"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
) -> None:
    """Remove a watch topic."""
    config = PaperExpertConfig.load()
    lib = Library(config)
    topic = lib.get_watch_topic(watch_id)
    if not topic:
        console.print(f"[red]Watch topic {watch_id} not found.[/red]")
        raise typer.Exit(1)
    if not force:
        confirm = typer.confirm(
            f"Delete '{topic['name']}' (ID: {watch_id})?"
        )
        if not confirm:
            return
    lib.delete_watch_topic(watch_id)
    console.print(f"[green]Deleted #{watch_id}: {topic['name']}[/green]")


@monitor_app.command("toggle-watch")
def toggle_watch(
    watch_id: int = typer.Argument(help="Watch topic ID"),
) -> None:
    """Enable or disable a watch topic."""
    config = PaperExpertConfig.load()
    lib = Library(config)
    topic = lib.get_watch_topic(watch_id)
    if not topic:
        console.print(f"[red]Watch topic {watch_id} not found.[/red]")
        raise typer.Exit(1)
    new_state = not topic["is_active"]
    lib.update_watch_topic(watch_id, is_active=new_state)
    s = "[green]enabled[/green]" if new_state else "[dim]disabled[/dim]"
    console.print(f"#{watch_id}: {topic['name']} -> {s}")


@monitor_app.command("run")
def run_monitor(
    watch_id: int | None = typer.Option(
        None, "--watch-id", "-w",
        help="Run a specific watch topic. Omit to run all."
    ),
) -> None:
    """Execute monitoring: search for new papers and send notifications."""
    asyncio.run(_run_async(watch_id))


async def _run_async(watch_id: int | None) -> None:
    config = PaperExpertConfig.load()
    lib = Library(config)
    try:
        with console.status("Running monitor..."):
            result = await lib.run_monitor(watch_id=watch_id)
        if hasattr(result, "results"):
            console.print("\n[bold]Monitor Complete[/bold]")
            console.print(f"  Topics: {result.topics_checked}")
            console.print(f"  Found: {result.total_found}, Added: {result.total_added}")
            for r in result.results:
                if r.error:
                    console.print(f"  [red]{r.topic_name}: {r.error}[/red]")
                elif r.papers_added > 0:
                    console.print(
                        f"  [green]{r.topic_name}: +{r.papers_added}[/green]"
                    )
                    n = [k for k, v in r.notify_results.items() if v]
                    if n:
                        console.print(f"    Notified: {', '.join(n)}")
                else:
                    console.print(f"  {r.topic_name}: no new papers")
        else:
            if result.error:
                console.print(f"[red]{result.error}[/red]")
            elif result.papers_added > 0:
                console.print(
                    f"[green]{result.topic_name}: +{result.papers_added}[/green]"
                )
                for p in result.new_papers:
                    console.print(f"  - {p['title'][:80]}")
            else:
                console.print(f"{result.topic_name}: no new papers")
    finally:
        await lib.close()


@monitor_app.command("logs")
def show_logs(
    watch_id: int = typer.Argument(help="Watch topic ID"),
    limit: int = typer.Option(20, "--limit", "-n", help="Number of entries"),
) -> None:
    """Show monitoring logs for a watch topic."""
    config = PaperExpertConfig.load()
    lib = Library(config)
    topic = lib.get_watch_topic(watch_id)
    if not topic:
        console.print(f"[red]Watch topic {watch_id} not found.[/red]")
        raise typer.Exit(1)
    logs = lib.get_watch_logs(watch_id, limit=limit)
    if not logs:
        console.print(f"No logs for '{topic['name']}' yet.")
        return
    table = Table(title=f"Monitor Logs: {topic['name']}")
    table.add_column("Time", max_width=20)
    table.add_column("Found", width=6)
    table.add_column("Added", width=6)
    table.add_column("Notify", width=15)
    table.add_column("Error", max_width=40)
    for log in logs:
        table.add_row(
            log.get("run_at", "")[:16],
            str(log.get("papers_found", 0)),
            str(log.get("papers_added", 0)),
            log.get("notify_status", "-"),
            (log.get("error") or "")[:40],
        )
    console.print(table)
