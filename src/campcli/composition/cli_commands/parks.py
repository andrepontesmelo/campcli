"""Parks CLI sub-commands (parks list, show, drive-times)."""

from __future__ import annotations

import typer

from .. import cli as _cli
from ...application import catalog
from ...presentation import format as fmt

app = typer.Typer(no_args_is_help=True, help="Discover parks and sub-areas (maps).")


@app.command("list")
def parks_list(
    search: str | None = typer.Option(None, "--search", "-s"),
    distance: str | None = typer.Option(
        None,
        "--distance",
        "-d",
        help="Max drive time. Accepts '2h30m', '90m', '1.5h', or a bare number (hours).",
    ),
) -> None:
    max_hours = _cli._parse_hours_or_exit(distance)
    drive_times = _cli.load_drive_times()
    with _cli.api_call() as api:
        parks = catalog.list_parks_filtered(
            api, drive_times=drive_times, search=search, max_hours=max_hours
        )
    typer.echo(fmt.render_parks(parks, drive_times))


@app.command("drive-times")
def parks_drive_times(
    refresh: bool = typer.Option(
        False, "--refresh", help="Re-geocode and re-route every park."
    ),
) -> None:
    with _cli.api_call() as api:
        parks = api.list_parks()

    def progress(i: int, n: int, name: str, status: str) -> None:
        typer.echo(f"  [{i}/{n}] {name}: {status}")

    cache = _cli.build_drive_cache(parks, refresh=refresh, progress=progress)
    routed = sum(1 for v in cache.values() if v.get("hours") is not None)
    typer.echo(f"drive times for {routed}/{len(parks)} parks at {_cli.DRIVE_TIMES_PATH}")


@app.command("show")
def parks_show(park_id: int = typer.Argument(...)) -> None:
    with _cli.api_call() as api:
        parks = api.list_parks()
        park = catalog.find_park(parks, park_id)
        if park is None:
            typer.echo(f"park {park_id} not found", err=True)
            raise typer.Exit(code=2)
        maps = api.list_maps(park_id)
    typer.echo(fmt.render_park_detail(park, maps, _cli.load_drive_times()))
