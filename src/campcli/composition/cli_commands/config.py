"""Config CLI sub-commands (config set-interval, config show)."""

from __future__ import annotations

import typer

from .. import cli as _cli

app = typer.Typer(no_args_is_help=True, help="Manage global settings.")


@app.command("set-interval")
def config_set_interval(
    secs: float = typer.Argument(
        ..., help="Minimum seconds between HTTP requests (must be > 0)."
    ),
) -> None:
    if secs <= 0:
        typer.echo("error: interval must be > 0", err=True)
        raise typer.Exit(code=1)
    _cli._store().set_setting(_cli.SETTING_REQUEST_INTERVAL_KEY, str(secs))
    typer.echo(f"request interval set to {secs}s")


@app.command("show")
def config_show() -> None:
    raw = _cli._store().get_setting(_cli.SETTING_REQUEST_INTERVAL_KEY)
    if raw is None:
        typer.echo(f"request_interval_secs: {_cli.DEFAULT_REQUEST_INTERVAL_SECS}s (default)")
    else:
        typer.echo(f"request_interval_secs: {raw}s")
