"""CLI command definitions for Paper Expert."""

import typer

app = typer.Typer(
    name="paper_expert",
    help="AI-powered academic paper management and research assistant.",
    no_args_is_help=True,
)


@app.callback()
def main(
    verbose: int = typer.Option(0, "--verbose", "-v", count=True, help="Increase verbosity"),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress non-error output"),
) -> None:
    """Paper Expert �?AI-powered paper management."""
    from paper_expert.core.logging import setup_logging

    if quiet:
        setup_logging(verbosity=-1)
    else:
        setup_logging(verbosity=verbose)

# Import command modules to register them with the app.
# These must be imported AFTER app is defined.
def _register_commands() -> None:
    from paper_expert.cli import (
        add,  # noqa: F401
        ask,  # noqa: F401
        campus,  # noqa: F401
        config,  # noqa: F401
        domain,  # noqa: F401
        expert,  # noqa: F401
        import_cmd,  # noqa: F401
        lib,  # noqa: F401
        monitor,  # noqa: F401
        read,  # noqa: F401
        review,  # noqa: F401
        search,  # noqa: F401
        suggest,  # noqa: F401
    )

_register_commands()
