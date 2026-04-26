"""Typer CLI. Each command is a thin shell over a service function."""
from __future__ import annotations

from datetime import date

import typer

import re

from . import format as fmt
from . import watches as watch_svc
from .drive_times import load_cache as load_drive_cache


_DURATION_RE = re.compile(
    r"^\s*(?:(\d+(?:\.\d+)?)\s*h)?\s*(?:(\d+(?:\.\d+)?)\s*m)?\s*$",
    re.IGNORECASE,
)


def _parse_hours(text: str) -> float:
    """Parse '2h30m', '90m', '1.5h', '3h', '45' (bare number = hours)."""
    s = text.strip()
    if not s:
        raise ValueError("empty duration")
    # Bare number → hours.
    try:
        return float(s)
    except ValueError:
        pass
    m = _DURATION_RE.match(s)
    if not m or not (m.group(1) or m.group(2)):
        raise ValueError(f"can't parse duration: {text!r} (try '2h30m', '90m', '1.5h')")
    h = float(m.group(1) or 0)
    minutes = float(m.group(2) or 0)
    return h + minutes / 60.0
from .api import ApiError, BCParksClient, RateLimited
from .availability import check_park
from .booking import quote_url
from .catalog import CATALOG_PATH, fetch_maps, find_park, get_parks
from .constants import BASE_URL, CONFIG_DIR, DB_PATH, DEFAULT_PROFILE, DRIVE_TIMES_PATH
from .drive_times import build_cache as build_drive_cache
from .search import run as run_search

app = typer.Typer(no_args_is_help=True, add_completion=False)
parks_app = typer.Typer(no_args_is_help=True, help="Discover parks and sub-areas (maps).")
watch_app = typer.Typer(no_args_is_help=True, help="Manage persistent availability watches.")
book_app = typer.Typer(no_args_is_help=True, help="Booking deep-link helpers.")
catalog_app = typer.Typer(no_args_is_help=True, help="Manage the cached park catalog.")
app.add_typer(parks_app, name="parks")
app.add_typer(watch_app, name="watch")
app.add_typer(book_app, name="book")
app.add_typer(catalog_app, name="catalog")


def _exit_for(err: Exception) -> typer.Exit:
    if isinstance(err, RateLimited):
        typer.echo(f"rate-limited: {err}", err=True)
        return typer.Exit(code=4)
    if isinstance(err, ApiError):
        typer.echo(f"upstream error: {err}", err=True)
        return typer.Exit(code=5)
    typer.echo(f"error: {err}", err=True)
    return typer.Exit(code=1)


# ----- parks -----------------------------------------------------------------

@parks_app.command("list")
def parks_list(
    search: str | None = typer.Option(None, "--search", "-s"),
    distance: str | None = typer.Option(
        None, "--distance", "-d",
        help="Max drive time. Accepts '2h30m', '90m', '1.5h', or a bare number (hours).",
    ),
) -> None:
    """List BC Parks campgrounds, sorted by drive time. Filter by name or max distance."""
    try:
        with BCParksClient() as client:
            parks = get_parks(client)
    except Exception as e:
        raise _exit_for(e) from e
    if search:
        q = search.lower()
        parks = [p for p in parks if q in p.name.lower()]
    if distance:
        try:
            max_hours = _parse_hours(distance)
        except ValueError as e:
            typer.echo(f"error: {e}", err=True)
            raise typer.Exit(code=1) from e
        cache = load_drive_cache()
        parks = [
            p for p in parks
            if (h := cache.get(p.park_id, {}).get("hours")) is not None and h <= max_hours
        ]
    typer.echo(fmt.render_parks(parks))


@parks_app.command("drive-times")
def parks_drive_times(
    refresh: bool = typer.Option(False, "--refresh", help="Re-geocode and re-route every park."),
) -> None:
    """One-off: geocode each park and compute drive hours from Coquitlam.

    Uses Nominatim (OSM) and OSRM public servers — free, no API key. Runs
    sequentially at ~1 req/sec; ~3-4 minutes for the full catalog. Results
    persist to ~/.campcli/drive_times.json and are read by `parks list`.
    """
    try:
        with BCParksClient() as client:
            parks = get_parks(client)
    except Exception as e:
        raise _exit_for(e) from e

    def progress(i: int, n: int, name: str, status: str) -> None:
        typer.echo(f"  [{i}/{n}] {name}: {status}")

    cache = build_drive_cache(parks, refresh=refresh, progress=progress)
    routed = sum(1 for v in cache.values() if v.get("hours") is not None)
    typer.echo(f"drive times for {routed}/{len(parks)} parks at {DRIVE_TIMES_PATH}")


@parks_app.command("show")
def parks_show(park_id: int = typer.Argument(...)) -> None:
    """Show a park and its maps (sub-areas)."""
    try:
        with BCParksClient() as client:
            parks = get_parks(client)
            park = find_park(parks, park_id)
            if park is None:
                typer.echo(f"park {park_id} not found", err=True)
                raise typer.Exit(code=2)
            maps = fetch_maps(client, park_id)
    except typer.Exit:
        raise
    except Exception as e:
        raise _exit_for(e) from e
    typer.echo(fmt.render_park_detail(park, maps))


# ----- check -----------------------------------------------------------------

@app.command("check")
def check(
    park: int = typer.Option(..., "--park", "-p"),
    start: str = typer.Option(..., "--start", help="YYYY-MM-DD"),
    nights: int = typer.Option(..., "--nights", "-n"),
    party_size: int = typer.Option(1, "--party-size"),
    map_id: int | None = typer.Option(None, "--map", help="Limit to one map (sub-area)."),
) -> None:
    """Check current availability for a park over a date range."""
    start_d = date.fromisoformat(start)
    try:
        with BCParksClient() as client:
            parks = get_parks(client)
            p = find_park(parks, park)
            if p is None:
                typer.echo(f"park {park} not found", err=True)
                raise typer.Exit(code=2)
            sites = check_park(client, p, start_d, nights, party_size, map_filter=map_id)
    except typer.Exit:
        raise
    except Exception as e:
        raise _exit_for(e) from e
    typer.echo(fmt.render_available_list(sites))
    if not sites:
        raise typer.Exit(code=3)


# ----- search ----------------------------------------------------------------

@app.command("search")
def search_cmd(
    months: int | None = typer.Option(None, "--months", help="Override profile horizon (months)."),
    distance: str | None = typer.Option(
        None, "--distance", "-d",
        help="Override max drive time (e.g. '4h', '3h30m', '210m').",
    ),
    limit_parks: int | None = typer.Option(None, "--limit-parks", hidden=True),
) -> None:
    """Find campsites matching your profile (currently hardcoded: weekends, 4h drive, 3 months)."""
    profile = dict(DEFAULT_PROFILE)
    if months is not None:
        profile["horizon_months"] = months
    if distance is not None:
        try:
            profile["max_drive_hours"] = _parse_hours(distance)
        except ValueError as e:
            typer.echo(f"error: {e}", err=True)
            raise typer.Exit(code=1) from e

    def progress(msg: str) -> None:
        typer.echo(msg, err=True)

    try:
        with BCParksClient() as client:
            matches = run_search(client, profile, limit_parks=limit_parks, progress=progress)
    except Exception as e:
        raise _exit_for(e) from e
    typer.echo(fmt.render_search_results(matches))
    if not matches:
        raise typer.Exit(code=3)


# ----- watch -----------------------------------------------------------------

@watch_app.command("add")
def watch_add(
    park: int = typer.Option(..., "--park", "-p"),
    start: str = typer.Option(..., "--start"),
    nights: int = typer.Option(..., "--nights", "-n"),
    party_size: int = typer.Option(1, "--party-size"),
    label: str | None = typer.Option(None, "--label"),
) -> None:
    """Persist a watch. Use `watch run` to scan."""
    w = watch_svc.add(park, date.fromisoformat(start), nights, party_size, label)
    typer.echo(fmt.render_watch(w))


@watch_app.command("list")
def watch_list() -> None:
    """List stored watches."""
    typer.echo(fmt.render_watches(watch_svc.list_all()))


@watch_app.command("rm")
def watch_rm(watch_id: int = typer.Argument(...)) -> None:
    """Remove a watch by id."""
    if not watch_svc.remove(watch_id):
        typer.echo(f"watch {watch_id} not found", err=True)
        raise typer.Exit(code=2)
    typer.echo(f"removed watch {watch_id}")


@watch_app.command("run")
def watch_run(
    watch_id: int | None = typer.Option(None, "--watch-id"),
) -> None:
    """Scan all watches (or one) once. Prints currently-available sites."""
    try:
        with BCParksClient() as client:
            results = watch_svc.run_all(client, watch_id=watch_id)
    except Exception as e:
        raise _exit_for(e) from e
    if not results:
        typer.echo("no watches" if watch_id is None else f"watch {watch_id} not found")
        raise typer.Exit(code=2 if watch_id is not None else 0)
    any_available = False
    for w, sites in results:
        header = f"== {fmt.render_watch(w)} =="
        if sites:
            any_available = True
            typer.echo(header)
            typer.echo(fmt.render_available_list(sites))
        else:
            typer.echo(f"{header}\nno availability")
    if not any_available:
        raise typer.Exit(code=3)


# ----- book ------------------------------------------------------------------

@book_app.command("quote")
def book_quote(
    park: int = typer.Option(..., "--park", "-p"),
    map_id: int = typer.Option(..., "--map", "-m"),
    start: str = typer.Option(..., "--start"),
    nights: int = typer.Option(..., "--nights", "-n"),
    party_size: int = typer.Option(1, "--party-size"),
) -> None:
    """Print a deep-link URL into the BC Parks booking flow."""
    typer.echo(
        quote_url(
            park_id=park,
            map_id=map_id,
            start=date.fromisoformat(start),
            nights=nights,
            party_size=party_size,
        )
    )


# ----- catalog ---------------------------------------------------------------

@catalog_app.command("refresh")
def catalog_refresh() -> None:
    """Force-refresh the on-disk park catalog cache."""
    try:
        with BCParksClient() as client:
            parks = get_parks(client, refresh=True)
    except Exception as e:
        raise _exit_for(e) from e
    typer.echo(f"cached {len(parks)} parks at {CATALOG_PATH}")


# ----- doctor ----------------------------------------------------------------

@app.command("doctor")
def doctor() -> None:
    """Verify API reachability and print config paths."""
    typer.echo(f"config dir:  {CONFIG_DIR}")
    typer.echo(f"db:          {DB_PATH}  (exists={DB_PATH.exists()})")
    typer.echo(f"catalog:     {CATALOG_PATH}  (exists={CATALOG_PATH.exists()})")
    typer.echo(f"api base:    {BASE_URL}")
    try:
        with BCParksClient() as client:
            n = len(client.list_resource_locations())
        typer.echo(f"api ok:      /api/resourceLocation returned {n} locations")
    except Exception as e:
        typer.echo(f"api error:   {e}", err=True)
        raise typer.Exit(code=5) from e


if __name__ == "__main__":
    app()
