"""Typer CLI. Each command is a thin shell over a service function."""
from __future__ import annotations

import os
import re
import webbrowser
from contextlib import contextmanager
from datetime import date

import typer

from . import bookings
from . import blocked
from . import catalog
from . import daemon as daemon_svc
from . import format as fmt
from . import search
from . import watches as watch_svc
from .api import BCParksClient
from .availability import check_park
from .booking import quote_url
from .clock import SystemClock
from .constants import BASE_URL, CATALOG_PATH, CONFIG_DIR, DB_PATH, DRIVE_TIMES_PATH
from .drive_times import build_cache as build_drive_cache
from .drive_times import load_cache as load_drive_times
from .ports import ApiError, RateLimited
from .store import SqliteStore


_DURATION_RE = re.compile(
    r"^\s*(?:(\d+(?:\.\d+)?)\s*h)?\s*(?:(\d+(?:\.\d+)?)\s*m)?\s*$",
    re.IGNORECASE,
)


def _parse_hours(text: str) -> float:
    s = text.strip()
    if not s:
        raise ValueError("empty duration")
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


def _parse_hours_or_exit(text: str | None) -> float | None:
    if text is None:
        return None
    try:
        return _parse_hours(text)
    except ValueError as e:
        typer.echo(f"error: {e}", err=True)
        raise typer.Exit(code=1) from e


def _parse_date_or_exit(text: str) -> date:
    try:
        return date.fromisoformat(text)
    except ValueError as e:
        typer.echo(f"error: invalid date {text!r}", err=True)
        raise typer.Exit(code=1) from e


def _exit_for(err: Exception) -> typer.Exit:
    if isinstance(err, RateLimited):
        typer.echo(f"rate-limited: {err}", err=True)
        return typer.Exit(code=4)
    if isinstance(err, ApiError):
        typer.echo(f"upstream error: {err}", err=True)
        return typer.Exit(code=5)
    if isinstance(err, ValueError):
        typer.echo(f"error: {err}", err=True)
        return typer.Exit(code=2)
    typer.echo(f"error: {err}", err=True)
    return typer.Exit(code=1)


def _store() -> SqliteStore:
    return SqliteStore(DB_PATH)


_CLOCK = SystemClock()


@contextmanager
def api_call():
    try:
        with BCParksClient() as api:
            yield api
    except typer.Exit:
        raise
    except Exception as e:
        raise _exit_for(e) from e


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


# ----- parks -----------------------------------------------------------------

@parks_app.command("list")
def parks_list(
    search: str | None = typer.Option(None, "--search", "-s"),
    distance: str | None = typer.Option(
        None, "--distance", "-d",
        help="Max drive time. Accepts '2h30m', '90m', '1.5h', or a bare number (hours).",
    ),
) -> None:
    max_hours = _parse_hours_or_exit(distance)
    drive_times = load_drive_times()
    with api_call() as api:
        parks = catalog.list_parks_filtered(
            api, drive_times=drive_times, search=search, max_hours=max_hours
        )
    typer.echo(fmt.render_parks(parks, drive_times))


@parks_app.command("drive-times")
def parks_drive_times(
    refresh: bool = typer.Option(False, "--refresh", help="Re-geocode and re-route every park."),
) -> None:
    with api_call() as api:
        parks = api.list_parks()

    def progress(i: int, n: int, name: str, status: str) -> None:
        typer.echo(f"  [{i}/{n}] {name}: {status}")

    cache = build_drive_cache(parks, refresh=refresh, progress=progress)
    routed = sum(1 for v in cache.values() if v.get("hours") is not None)
    typer.echo(f"drive times for {routed}/{len(parks)} parks at {DRIVE_TIMES_PATH}")


@parks_app.command("show")
def parks_show(park_id: int = typer.Argument(...)) -> None:
    with api_call() as api:
        parks = api.list_parks()
        park = catalog.find_park(parks, park_id)
        if park is None:
            typer.echo(f"park {park_id} not found", err=True)
            raise typer.Exit(code=2)
        maps = api.list_maps(park_id)
    typer.echo(fmt.render_park_detail(park, maps, load_drive_times()))


# ----- check -----------------------------------------------------------------

@app.command("check")
def check(
    park: int = typer.Option(..., "--park", "-p"),
    start: str = typer.Option(..., "--start", help="YYYY-MM-DD"),
    nights: int = typer.Option(..., "--nights", "-n"),
    party_size: int = typer.Option(1, "--party-size"),
    map_id: int | None = typer.Option(None, "--map", help="Limit to one map (sub-area)."),
) -> None:
    start_d = _parse_date_or_exit(start)
    with api_call() as api:
        parks = api.list_parks()
        p = catalog.find_park(parks, park)
        if p is None:
            typer.echo(f"park {park} not found", err=True)
            raise typer.Exit(code=2)
        sites = check_park(api, p, start_d, nights, party_size, map_filter=map_id)
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
    if group_by not in ("weekend", "park"):
        typer.echo("error: --group-by must be 'weekend' or 'park'", err=True)
        raise typer.Exit(code=1)
    profile = search.build_profile(months=months, max_hours=_parse_hours_or_exit(distance))
    drive_times = load_drive_times()

    def progress(msg: str) -> None:
        typer.echo(msg, err=True)

    with api_call() as api:
        matches = search.run(
            api, profile, drive_times=drive_times,
            limit_parks=limit_parks, progress=progress,
        )
    typer.echo(fmt.render_search_results(
        matches, group_by=group_by, with_urls=with_urls, drive_times=drive_times,
    ))
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
    w = watch_svc.add(park, _parse_date_or_exit(start), nights, party_size, label,
                      watch_repo=_store(), clock=_CLOCK)
    typer.echo(fmt.render_watch(w))


@watch_app.command("list")
def watch_list() -> None:
    typer.echo(fmt.render_watches(_store().list_watches()))


@watch_app.command("rm")
def watch_rm(watch_id: int = typer.Argument(...)) -> None:
    if not _store().remove_watch(watch_id):
        typer.echo(f"watch {watch_id} not found", err=True)
        raise typer.Exit(code=2)
    typer.echo(f"removed watch {watch_id}")


@watch_app.command("run")
def watch_run(
    watch_id: int | None = typer.Option(None, "--watch-id"),
) -> None:
    with api_call() as api:
        results = watch_svc.run_all(api, watch_repo=_store(), watch_id=watch_id)
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
    start_d = _parse_date_or_exit(start)
    url = quote_url(
        park_id=park,
        map_id=map_id,
        start=start_d,
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
    start_d = _parse_date_or_exit(start)
    typer.echo(
        quote_url(
            park_id=park,
            map_id=map_id,
            start=start_d,
            nights=nights,
            party_size=party_size,
        )
    )


# ----- catalog ---------------------------------------------------------------

@catalog_app.command("refresh")
def catalog_refresh() -> None:
    with api_call() as api:
        parks = api.list_parks(refresh=True)
    typer.echo(f"cached {len(parks)} parks at {CATALOG_PATH}")


# ----- doctor ----------------------------------------------------------------

@app.command("doctor")
def doctor() -> None:
    """Verify API reachability and print config paths.

    Adapter-aware: calls BCParksClient.list_resource_locations() off-Protocol.
    Diagnostic tool, not Application code.
    """
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

@bookings_app.command("list")
def bookings_list() -> None:
    rows = _store().list_bookings()
    if not rows:
        typer.echo("no bookings")
        return
    for b in rows:
        typer.echo(fmt.render_booking(b))


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
    start_d = _parse_date_or_exit(start)
    with api_call() as api:
        saved = bookings.add(
            api, park_query=park, start=start_d, nights=nights,
            map_name=map_name, site=site,
            party_size=party, fee=fee, notes=notes,
            booking_repo=_store(), clock=_CLOCK,
        )
    typer.echo(fmt.render_booking(saved))


@bookings_app.command("rm")
def bookings_rm(booking_id: int = typer.Argument(...)) -> None:
    if not _store().remove_booking(booking_id):
        typer.echo(f"booking {booking_id} not found", err=True)
        raise typer.Exit(code=2)
    typer.echo(f"removed booking {booking_id}")


# ----- blocked ---------------------------------------------------------------

@blocked_app.command("list")
def blocked_list() -> None:
    rows = _store().list_blocked()
    if not rows:
        typer.echo("no blocked parks")
        return
    for bp in rows:
        typer.echo(f"{bp.park_id}\t{bp.park_name}")


@blocked_app.command("add")
def blocked_add(park: str = typer.Argument(..., help="Park name (substring or exact).")) -> None:
    with api_call() as api:
        bp = blocked.add(api, park, blocked_repo=_store(), clock=_CLOCK)
    typer.echo(f"blocked: {bp.park_name} (id={bp.park_id})")


@blocked_app.command("rm")
def blocked_rm(park: str = typer.Argument(..., help="Park name or numeric id.")) -> None:
    with api_call() as api:
        removed = blocked.remove(api, park, blocked_repo=_store())
    if not removed:
        typer.echo(f"park {park} not in blocklist", err=True)
        raise typer.Exit(code=2)
    typer.echo(f"unblocked {park}")


# ----- daemon ----------------------------------------------------------------

@app.command("daemon")
def daemon_cmd(
    interval: float = typer.Option(1.0, "--interval", help="Seconds to sleep between polls."),
) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        typer.echo("error: set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID", err=True)
        raise typer.Exit(code=2)
    daemon_svc.run_forever(bot_token=token, chat_id=chat_id, interval_secs=interval)


if __name__ == "__main__":
    app()
