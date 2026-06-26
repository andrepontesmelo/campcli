"""Book CLI sub-commands (book open, book quote)."""

from __future__ import annotations

import webbrowser

import typer

from .. import cli as _cli

app = typer.Typer(no_args_is_help=True, help="Booking deep-link helpers.")


@app.command("open")
def book_open(
    park: int = typer.Option(..., "--park", "-p"),
    map_id: int = typer.Option(..., "--map", "-m"),
    start: str = typer.Option(..., "--start"),
    nights: int = typer.Option(..., "--nights", "-n"),
    party_size: int = typer.Option(1, "--party-size"),
) -> None:
    start_d = _cli._parse_date_or_exit(start)
    url = _cli.book_open_uc(
        park_id=park, map_id=map_id, start=start_d, nights=nights, party_size=party_size
    )
    typer.echo(url)
    if not webbrowser.open(url):
        typer.echo("(could not launch a browser — copy the URL above)", err=True)
        raise typer.Exit(code=1)


@app.command("quote")
def book_quote(
    park: int = typer.Option(..., "--park", "-p"),
    map_id: int = typer.Option(..., "--map", "-m"),
    start: str = typer.Option(..., "--start"),
    nights: int = typer.Option(..., "--nights", "-n"),
    party_size: int = typer.Option(1, "--party-size"),
) -> None:
    start_d = _cli._parse_date_or_exit(start)
    url = _cli.book_quote_uc(
        park_id=park, map_id=map_id, start=start_d, nights=nights, party_size=party_size
    )
    typer.echo(url)
