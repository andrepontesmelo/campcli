"""Typer CLI. Each command is a thin shell over a service function."""
from __future__ import annotations

import os
import webbrowser
from datetime import date, timedelta

import typer

import re

from . import daemon as daemon_svc
from . import format as fmt
from . import store
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
from .api import BCParksClient
from .availability import check_park
from .booking import quote_url
from .catalog import find_park, resolve_park
from .constants import BASE_URL, CATALOG_PATH, CONFIG_DIR, DB_PATH, DEFAULT_PROFILE, DRIVE_TIMES_PATH
from .ports import ApiError, RateLimited
from .drive_times import build_cache as build_drive_cache
from .models import Booking
from .search import run as run_search

app = typer.Typer(no_args_is_help=True, add_completion=False)
parks_app = typer.Typer(no_args_is_help=True, help="Discover parks and sub-areas (maps).")
watch_app = typer.Typer(no_args_is_help=True, help="Manage persistent availability watches.")
book_app = typer.Typer(no_args_is_help=True, help="Booking deep-link helpers.")
catalog_app = typer.Typer(no_args_is_help=True, help="Manage the cached park catalog.")
bookings_app = typer.Typer(no_args_is_help=True, help="Manage existing campsite bookings.")
blocked_app = typer.Typer(no_args_is_help=True, help="Manage the blocklist of unwanted parks.")
app.add_typer(parks_app, name="parks")
app.add_typer(watch_app, name="watch")
app.add_typer(book_app, name="book")
app.add_typer(catalog_app, name="catalog")
app.add_typer(bookings_app, name="bookings")
app.add_typer(blocked_app, name="blocked")


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
            parks = client.list_parks()
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
            parks = client.list_parks()
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
            parks = client.list_parks()
            park = find_park(parks, park_id)
            if park is None:
                typer.echo(f"park {park_id} not found", err=True)
                raise typer.Exit(code=2)
            maps = client.list_maps(park_id)
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
            parks = client.list_parks()
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
    group_by: str = typer.Option(
        "weekend", "--group-by", "-g",
        help="Top-level grouping: 'weekend' (default) or 'park'.",
    ),
    with_urls: bool = typer.Option(
        False, "--with-urls", "-u",
        help="Print a clickable booking deep-link under each match.",
    ),
    limit_parks: int | None = typer.Option(None, "--limit-parks", hidden=True),
) -> None:
    """Find campsites matching your profile (currently hardcoded: weekends, 4h drive, 3 months)."""
    if group_by not in ("weekend", "park"):
        typer.echo("error: --group-by must be 'weekend' or 'park'", err=True)
        raise typer.Exit(code=1)
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
    typer.echo(fmt.render_search_results(matches, group_by=group_by, with_urls=with_urls))
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

@book_app.command("open")
def book_open(
    park: int = typer.Option(..., "--park", "-p"),
    map_id: int = typer.Option(..., "--map", "-m"),
    start: str = typer.Option(..., "--start"),
    nights: int = typer.Option(..., "--nights", "-n"),
    party_size: int = typer.Option(1, "--party-size"),
) -> None:
    """Open the BC Parks booking deep-link in the default browser."""
    url = quote_url(
        park_id=park,
        map_id=map_id,
        start=date.fromisoformat(start),
        nights=nights,
        party_size=party_size,
    )
    typer.echo(url)
    if not webbrowser.open(url):
        typer.echo("(could not launch a browser — copy the URL above)", err=True)
        raise typer.Exit(code=1)


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
            parks = client.list_parks(refresh=True)
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


# ----- bookings --------------------------------------------------------------

def _render_booking(b: Booking) -> str:
    site = f" #{b.site_name}" if b.site_name else ""
    map_part = f" — {b.map_name}" if b.map_name else ""
    fee = f" ${b.fee:.2f}" if b.fee is not None else ""
    party = f" party={b.party_size}" if b.party_size is not None else ""
    notes = f"  ({b.notes})" if b.notes else ""
    return (
        f"#{b.id}  {b.park_name}{map_part}{site}  "
        f"{b.start_date.isoformat()} → {b.end_date.isoformat()}{fee}{party}{notes}"
    )


@bookings_app.command("list")
def bookings_list() -> None:
    rows = store.list_bookings()
    if not rows:
        typer.echo("no bookings")
        return
    for b in rows:
        typer.echo(_render_booking(b))


@bookings_app.command("add")
def bookings_add(
    park: str = typer.Option(..., "--park", help="Park name (substring or exact)."),
    start: str = typer.Option(..., "--start", help="YYYY-MM-DD check-in date."),
    nights: int = typer.Option(..., "--nights", "-n"),
    map_name: str | None = typer.Option(None, "--map", help="Sub-area / loop name."),
    site: str | None = typer.Option(None, "--site", help="Site label, e.g. B31."),
    party: int | None = typer.Option(None, "--party"),
    fee: float | None = typer.Option(None, "--fee"),
    notes: str | None = typer.Option(None, "--notes"),
) -> None:
    """Record a confirmed booking. Used to suppress notifications for adjacent weekends."""
    try:
        with BCParksClient() as client:
            p = resolve_park(client, park)
    except ValueError as e:
        typer.echo(f"error: {e}", err=True)
        raise typer.Exit(code=2) from e
    except Exception as e:
        raise _exit_for(e) from e
    start_d = date.fromisoformat(start)
    b = Booking(
        park_id=p.park_id,
        park_name=p.name,
        map_name=map_name,
        site_name=site,
        start_date=start_d,
        end_date=start_d + timedelta(days=nights),
        party_size=party,
        fee=fee,
        notes=notes,
    )
    saved = store.add_booking(b)
    typer.echo(_render_booking(saved))


@bookings_app.command("rm")
def bookings_rm(booking_id: int = typer.Argument(...)) -> None:
    if not store.remove_booking(booking_id):
        typer.echo(f"booking {booking_id} not found", err=True)
        raise typer.Exit(code=2)
    typer.echo(f"removed booking {booking_id}")


# ----- blocked ---------------------------------------------------------------

@blocked_app.command("list")
def blocked_list() -> None:
    rows = store.list_blocked_parks()
    if not rows:
        typer.echo("no blocked parks")
        return
    for bp in rows:
        typer.echo(f"{bp.park_id}\t{bp.park_name}")


@blocked_app.command("add")
def blocked_add(park: str = typer.Argument(..., help="Park name (substring or exact).")) -> None:
    try:
        with BCParksClient() as client:
            p = resolve_park(client, park)
    except ValueError as e:
        typer.echo(f"error: {e}", err=True)
        raise typer.Exit(code=2) from e
    except Exception as e:
        raise _exit_for(e) from e
    bp = store.add_blocked_park(p.park_id, p.name)
    typer.echo(f"blocked: {bp.park_name} (id={bp.park_id})")


@blocked_app.command("rm")
def blocked_rm(park: str = typer.Argument(..., help="Park name or numeric id.")) -> None:
    if park.isdigit():
        park_id = int(park)
    else:
        try:
            with BCParksClient() as client:
                p = resolve_park(client, park)
        except ValueError as e:
            typer.echo(f"error: {e}", err=True)
            raise typer.Exit(code=2) from e
        park_id = p.park_id
    if not store.remove_blocked_park(park_id):
        typer.echo(f"park {park_id} not in blocklist", err=True)
        raise typer.Exit(code=2)
    typer.echo(f"unblocked {park_id}")


# ----- daemon ----------------------------------------------------------------

@app.command("daemon")
def daemon_cmd(
    interval: float = typer.Option(1.0, "--interval", help="Seconds to sleep between polls."),
) -> None:
    """Long-running poller. Sends a Telegram message ASAP for each new match.

    Requires env vars TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID.
    Suppresses matches in blocked parks and within 14 days of an existing booking.
    """
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        typer.echo("error: set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID", err=True)
        raise typer.Exit(code=2)
    daemon_svc.run_forever(bot_token=token, chat_id=chat_id, interval_secs=interval)


if __name__ == "__main__":
    app()
