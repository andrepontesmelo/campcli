"""Catalog CLI sub-command (catalog refresh)."""

from __future__ import annotations

import typer

from .. import cli as _cli

app = typer.Typer(no_args_is_help=True, help="Manage the cached park catalog.")


@app.command("refresh")
def catalog_refresh() -> None:
    with _cli.api_call() as api:
        parks = api.list_parks(refresh=True)
    typer.echo(f"cached {len(parks)} parks at {_cli.CATALOG_PATH}")
