"""Typer CLI. Each command is a thin shell over a service function."""
from __future__ import annotations

import os
import re
import webbrowser
from contextlib import contextmanager
from datetime import date

import typer

from ..application import catalog
from . import daemon as daemon_svc
from ..presentation import format as fmt
from ..infrastructure.api import BCParksClient
from ..application.not_interested import (
    not_interested_add as not_interested_add_uc,
    not_interested_rm as not_interested_rm_uc,
    not_interested_list as not_interested_list_uc,
)
from ..application.profile import (
    resolve_profile,
    profile_create as profile_create_uc,
    profile_list as profile_list_uc,
    profile_show as profile_show_uc,
    profile_edit as profile_edit_uc,
    profile_delete as profile_delete_uc,
    profile_enable as profile_enable_uc,
    profile_disable as profile_disable_uc,
    profile_tg_add as profile_tg_add_uc,
    profile_tg_rm as profile_tg_rm_uc,
    profile_tg_list as profile_tg_list_uc,
    profile_search as profile_search_uc,
)
from ..application.search import (
    _search_for_profile,
    check as check_uc,
    book_open as book_open_uc,
    book_quote as book_quote_uc,
)
from ..infrastructure.clock import SystemClock
from ..application.migrate_profile import migrate_profile_json_to_db
from ..application.throttle import (
    SETTING_REQUEST_INTERVAL_KEY,
    read_request_interval,
)
from ..constants import DEFAULT_REQUEST_INTERVAL_SECS
from ..constants import BASE_URL, CATALOG_PATH, CONFIG_DIR, DB_PATH, DRIVE_TIMES_PATH, PROFILE_PATH
from ..infrastructure.drive_times_cache import build_cache as build_drive_cache
from ..infrastructure.drive_times_cache import load_cache as load_drive_times
from ..domain.ports import ApiError, RateLimited
from ..infrastructure.store import SqliteStore


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
        raise typer.Exit(code=2) from e


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
    interval = read_request_interval(_store())
    try:
        with BCParksClient(min_interval_secs=interval) as api:
            yield api
    except typer.Exit:
        raise
    except Exception as e:
        raise _exit_for(e) from e


app = typer.Typer(no_args_is_help=True, add_completion=False)
parks_app = typer.Typer(no_args_is_help=True, help="Discover parks and sub-areas (maps).")
book_app = typer.Typer(no_args_is_help=True, help="Booking deep-link helpers.")
catalog_app = typer.Typer(no_args_is_help=True, help="Manage the cached park catalog.")
app.add_typer(parks_app, name="parks")
app.add_typer(book_app, name="book")
app.add_typer(catalog_app, name="catalog")
config_app = typer.Typer(no_args_is_help=True, help="Manage global settings.")
app.add_typer(config_app, name="config")
profile_app = typer.Typer(no_args_is_help=True, help="Manage search profiles.")
app.add_typer(profile_app, name="profile")


@app.callback()
def _main_callback() -> None:
    """Run once before any subcommand: migrate legacy profile.json to DB."""
    _run_profile_migration()


# ----- helpers ----------------------------------------------------------------


def _run_profile_migration() -> None:
    """Migrate legacy profile.json to DB if needed. Safe to call on every command."""
    store = _store()
    migrate_profile_json_to_db(PROFILE_PATH, store)



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
    profile_name: str | None = typer.Option(
        None, "--profile", "-P",
        help="Profile name (uses the single enabled profile if omitted).",
    ),
) -> None:
    store = _store()
    profile = resolve_profile(store, profile_name)
    start_d = _parse_date_or_exit(start)
    with api_call() as api:
        check_uc(api, profile, park, start_d, nights, party_size, map_filter=map_id)


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
    profile_name: str | None = typer.Option(
        None, "--profile", "-P",
        help="Profile name (uses the single enabled profile if omitted).",
    ),
) -> None:
    """Search campsites using profile PARKS and PATTERNS (uses --profile or the single enabled profile)."""
    if group_by not in ("weekend", "park"):
        typer.echo("error: --group-by must be 'weekend' or 'park'", err=True)
        raise typer.Exit(code=1)

    store = _store()
    profile = resolve_profile(store, profile_name)
    typer.echo(f"Profile: {profile.name}", err=True)
    max_drive_hours = _parse_hours_or_exit(distance)
    drive_times = load_drive_times()
    with api_call() as api:
        _search_for_profile(
            profile, api=api, drive_times=drive_times,
            months=months, max_drive_hours=max_drive_hours,
            group_by=group_by, with_urls=with_urls, limit_parks=limit_parks,
        )


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
    url = book_open_uc(park_id=park, map_id=map_id, start=start_d, nights=nights, party_size=party_size)
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
    url = book_quote_uc(park_id=park, map_id=map_id, start=start_d, nights=nights, party_size=party_size)
    typer.echo(url)


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


# ----- config ----------------------------------------------------------------

@config_app.command("set-interval")
def config_set_interval(
    secs: float = typer.Argument(..., help="Minimum seconds between HTTP requests (must be > 0)."),
) -> None:
    if secs <= 0:
        typer.echo("error: interval must be > 0", err=True)
        raise typer.Exit(code=1)
    _store().set_setting(SETTING_REQUEST_INTERVAL_KEY, str(secs))
    typer.echo(f"request interval set to {secs}s")


@config_app.command("show")
def config_show() -> None:
    raw = _store().get_setting(SETTING_REQUEST_INTERVAL_KEY)
    if raw is None:
        typer.echo(f"request_interval_secs: {DEFAULT_REQUEST_INTERVAL_SECS}s (default)")
    else:
        typer.echo(f"request_interval_secs: {raw}s")


# ----- profile ---------------------------------------------------------------


@profile_app.command("create")
def profile_create(
    name: str = typer.Argument(..., help="Unique profile name."),
) -> None:
    """Create a new search profile with interactive prompts."""
    profile_create_uc(_store(), name)


@profile_app.command("list")
def profile_list() -> None:
    """List all profiles with key fields."""
    profile_list_uc(_store())


@profile_app.command("show")
def profile_show(
    name: str = typer.Argument(..., help="Profile name."),
) -> None:
    """Show full profile details."""
    profile_show_uc(_store(), name)


@profile_app.command("search")
def profile_search(
    name: str = typer.Argument(..., help="Profile name."),
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
    """Search campsites for a named profile (explicit form)."""
    max_drive_hours = _parse_hours_or_exit(distance)
    drive_times = load_drive_times()
    with api_call() as api:
        profile_search_uc(
            _store(), api, drive_times, name,
            months=months, max_drive_hours=max_drive_hours,
            group_by=group_by, with_urls=with_urls, limit_parks=limit_parks,
        )


@profile_app.command("enable")
def profile_enable(
    name: str = typer.Argument(..., help="Profile name."),
) -> None:
    """Enable a profile."""
    profile_enable_uc(_store(), name)


@profile_app.command("disable")
def profile_disable(
    name: str = typer.Argument(..., help="Profile name."),
) -> None:
    """Disable a profile."""
    profile_disable_uc(_store(), name)


@profile_app.command("delete")
def profile_delete(
    name: str = typer.Argument(..., help="Profile name."),
) -> None:
    """Delete a profile permanently."""
    profile_delete_uc(_store(), name)


# ----- profile tg-* commands -------------------------------------------------


@profile_app.command("tg-add")
def profile_tg_add(
    name: str = typer.Argument(..., help="Profile name."),
    tg_id: int = typer.Argument(..., help="Telegram user ID to authorize."),
) -> None:
    """Add a Telegram user ID to a profile."""
    profile_tg_add_uc(_store(), name, tg_id)


@profile_app.command("tg-rm")
def profile_tg_rm(
    name: str = typer.Argument(..., help="Profile name."),
    tg_id: int = typer.Argument(..., help="Telegram user ID to remove."),
) -> None:
    """Remove a Telegram user ID from a profile."""
    profile_tg_rm_uc(_store(), name, tg_id)


@profile_app.command("tg-list")
def profile_tg_list(
    name: str = typer.Argument(..., help="Profile name."),
) -> None:
    """List Telegram user IDs authorized for a profile."""
    profile_tg_list_uc(_store(), name)


# ----- profile edit ----------------------------------------------------------


@profile_app.command("edit")
def profile_edit(
    name: str = typer.Argument(..., help="Profile name."),
) -> None:
    """Edit a profile interactively — add/remove patterns, parks, Telegram IDs."""
    profile_edit_uc(_store(), name)


# ----- profile not-interested -------------------------------------------------

not_interested_app = typer.Typer(
    no_args_is_help=True, help="Manage not-interested entries (parks+dates to skip)."
)
profile_app.add_typer(not_interested_app, name="not-interested")


@not_interested_app.command("add")
def not_interested_add(
    profile_name: str = typer.Argument(..., help="Profile name."),
    park_name: str = typer.Argument(..., help="Park name."),
    date_start: str = typer.Argument(..., help="Start date (YYYY-MM-DD)."),
    date_end: str = typer.Argument(..., help="End date (YYYY-MM-DD)."),
) -> None:
    """Mark a park+dates as not interested for a profile."""
    store = _store()
    start = _parse_date_or_exit(date_start)
    end = _parse_date_or_exit(date_end)
    with api_call() as api:
        not_interested_add_uc(store, store, api, profile_name, park_name, start, end)


@not_interested_app.command("rm")
def not_interested_rm(
    profile_name: str = typer.Argument(..., help="Profile name."),
    park_name: str = typer.Argument(..., help="Park name."),
    date_start: str = typer.Argument(..., help="Start date (YYYY-MM-DD)."),
    date_end: str = typer.Argument(..., help="End date (YYYY-MM-DD)."),
) -> None:
    """Remove a not-interested entry."""
    store = _store()
    start = _parse_date_or_exit(date_start)
    end = _parse_date_or_exit(date_end)
    with api_call() as api:
        not_interested_rm_uc(store, store, api, profile_name, park_name, start, end)


@not_interested_app.command("list")
def not_interested_list(
    profile_name: str = typer.Argument(..., help="Profile name."),
) -> None:
    """List not-interested entries for a profile."""
    store = _store()
    with api_call() as api:
        not_interested_list_uc(store, store, api, profile_name)


# ----- daemon ----------------------------------------------------------------

@app.command("daemon")
def daemon_cmd(
    interval: float = typer.Option(1.0, "--interval", help="Seconds to sleep between polls."),
) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        typer.echo("error: set TELEGRAM_BOT_TOKEN", err=True)
        raise typer.Exit(code=2)
    daemon_svc.run_forever(bot_token=token, interval_secs=interval)


if __name__ == "__main__":
    app()
