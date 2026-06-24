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
from ..application import search
from ..infrastructure.api import BCParksClient
from ..application.availability import check_park
from ..application.booking_links import quote_url
from ..infrastructure.clock import SystemClock
from ..application.profile import Profile, load_profile
from ..application.throttle import (
    DEFAULT_REQUEST_INTERVAL_SECS,
    SETTING_REQUEST_INTERVAL_KEY,
    read_request_interval,
)
from ..constants import BASE_URL, CATALOG_PATH, CONFIG_DIR, DB_PATH, DRIVE_TIMES_PATH
from ..domain.booking_window import max_bookable_start
from ..domain.models import Profile
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
telegram_app = typer.Typer(no_args_is_help=True, help="Manage authorized Telegram users.")
app.add_typer(parks_app, name="parks")
app.add_typer(book_app, name="book")
app.add_typer(catalog_app, name="catalog")
app.add_typer(telegram_app, name="telegram")
config_app = typer.Typer(no_args_is_help=True, help="Manage global settings.")
app.add_typer(config_app, name="config")
profile_app = typer.Typer(no_args_is_help=True, help="Manage search profiles.")
app.add_typer(profile_app, name="profile")


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
    cutoff = max_bookable_start()
    if start_d > cutoff:
        typer.echo(f"Warning: {start_d} is beyond 3-month booking window (bookable through {cutoff}).", err=True)
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
    drive_times = load_drive_times()

    def progress(msg: str) -> None:
        typer.echo(msg, err=True)

    with api_call() as api:
        profile = load_profile(api)
        # CLI flags override profile values.
        if months is not None:
            profile.max_horizon_months = months
        parsed_distance = _parse_hours_or_exit(distance)
        if parsed_distance is not None:
            profile.max_drive_hours = parsed_distance

        allowed_ids = profile.allowed_park_ids or None
        matches = list(search.run(
            api, profile, drive_times=drive_times,
            allowed_park_ids=allowed_ids,
            limit_parks=limit_parks, progress=progress,
        ))
    typer.echo(fmt.render_search_results(
        matches, group_by=group_by, with_urls=with_urls, drive_times=drive_times,
    ))
    if not matches:
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
    cutoff = max_bookable_start()
    if start_d > cutoff:
        typer.echo(f"Warning: {start_d} is beyond 3-month booking window (bookable through {cutoff}).", err=True)
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
    cutoff = max_bookable_start()
    if start_d > cutoff:
        typer.echo(f"Warning: {start_d} is beyond 3-month booking window (bookable through {cutoff}).", err=True)
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


def _confirm_profile_exists(store: SqliteStore, name: str) -> Profile:
    profile = store.get_by_name(name)
    if profile is None:
        typer.echo(f"error: profile {name!r} not found", err=True)
        raise typer.Exit(code=2)
    return profile


@profile_app.command("create")
def profile_create(
    name: str = typer.Argument(..., help="Unique profile name."),
) -> None:
    """Create a new search profile with interactive prompts."""
    store = _store()
    if store.get_by_name(name) is not None:
        typer.echo(f"error: profile {name!r} already exists", err=True)
        raise typer.Exit(code=2)

    max_horizon_months = typer.prompt("Max horizon (months)", default=3, type=int)
    max_drive_hours = typer.prompt("Max drive (hours)", default=3.0, type=float)
    raw_date = typer.prompt("Min start date (YYYY-MM-DD, optional)", default="")
    min_start_date: str | None = raw_date.strip() or None
    if min_start_date is not None:
        try:
            date.fromisoformat(min_start_date)
        except ValueError:
            typer.echo(f"error: invalid date {min_start_date!r}", err=True)
            raise typer.Exit(code=2)
    rest_days = typer.prompt("Rest days between bookings", default=14, type=int)

    # TODO: Add interactive prompts for patterns, parks, telegram IDs
    #       in slice 7e85bx3w.

    profile = Profile(
        name=name,
        max_horizon_months=max_horizon_months,
        max_drive_hours=max_drive_hours,
        min_start_date=min_start_date,
        rest_days_between_bookings=rest_days,
    )
    created = store.create(profile)
    typer.echo(f"profile {name!r} created (id={created.id})")


@profile_app.command("list")
def profile_list() -> None:
    """List all profiles with key fields."""
    store = _store()
    profiles = store.list_all()
    if not profiles:
        typer.echo("no profiles")
        return
    header = f"{'Name':<24} {'Enabled':<9} {'Horizon':<9} {'Drive':<9} {'Rest':<6} {'Created'}"
    typer.echo(header)
    typer.echo("-" * len(header))
    for p in profiles:
        enabled = "yes" if p.enabled else "no"
        created = p.created_at[:10] if p.created_at else "-"
        typer.echo(
            f"{p.name:<24} {enabled:<9} {p.max_horizon_months:<9} "
            f"{p.max_drive_hours:<9} {p.rest_days_between_bookings:<6} {created}"
        )


@profile_app.command("show")
def profile_show(
    name: str = typer.Argument(..., help="Profile name."),
) -> None:
    """Show full profile details."""
    store = _store()
    profile = _confirm_profile_exists(store, name)
    typer.echo(f"name:                         {profile.name}")
    typer.echo(f"enabled:                      {'yes' if profile.enabled else 'no'}")
    typer.echo(f"max_horizon_months:           {profile.max_horizon_months}")
    typer.echo(f"max_drive_hours:              {profile.max_drive_hours}")
    typer.echo(f"min_start_date:               {profile.min_start_date or '-'}")
    typer.echo(f"rest_days_between_bookings:   {profile.rest_days_between_bookings}")
    typer.echo(f"patterns:                     {profile.patterns or '-'}")
    typer.echo(f"parks:                        {profile.parks or '-'}")
    typer.echo(f"tg_allowed_ids:               {profile.tg_allowed_ids or '-'}")
    typer.echo(f"created_at:                   {profile.created_at or '-'}")
    typer.echo(f"updated_at:                   {profile.updated_at or '-'}")


@profile_app.command("enable")
def profile_enable(
    name: str = typer.Argument(..., help="Profile name."),
) -> None:
    """Enable a profile."""
    store = _store()
    _confirm_profile_exists(store, name)
    store.set_enabled(name, True)
    typer.echo(f"profile {name!r} enabled")


@profile_app.command("disable")
def profile_disable(
    name: str = typer.Argument(..., help="Profile name."),
) -> None:
    """Disable a profile."""
    store = _store()
    _confirm_profile_exists(store, name)
    store.set_enabled(name, False)
    typer.echo(f"profile {name!r} disabled")


@profile_app.command("delete")
def profile_delete(
    name: str = typer.Argument(..., help="Profile name."),
) -> None:
    """Delete a profile permanently."""
    store = _store()
    _confirm_profile_exists(store, name)
    store.delete(name)
    typer.echo(f"profile {name!r} deleted")


# ----- telegram --------------------------------------------------------------

@telegram_app.command("allow")
def telegram_allow(
    tg_ids: list[int] = typer.Argument(..., help="Telegram user ID(s) to authorize."),
) -> None:
    """Add one or more Telegram user IDs to the authorized list."""
    profile_path = CONFIG_DIR / "profile.json"
    if not profile_path.exists():
        typer.echo("error: profile.json not found", err=True)
        raise typer.Exit(code=2)
    import json
    raw = json.loads(profile_path.read_text())
    allowed = raw.get("tg_allowed_ids", [])
    added = []
    for tid in tg_ids:
        if tid in allowed:
            continue
        allowed.append(tid)
        added.append(tid)
    raw["tg_allowed_ids"] = allowed
    profile_path.write_text(json.dumps(raw, indent=2) + "\n")
    if added:
        typer.echo(f"authorized: {', '.join(str(t) for t in added)}")
    else:
        typer.echo("all IDs already authorized")


@telegram_app.command("revoke")
def telegram_revoke(
    tg_ids: list[int] = typer.Argument(..., help="Telegram user ID(s) to revoke."),
) -> None:
    """Remove one or more Telegram user IDs from the authorized list."""
    profile_path = CONFIG_DIR / "profile.json"
    if not profile_path.exists():
        typer.echo("error: profile.json not found", err=True)
        raise typer.Exit(code=2)
    import json
    raw = json.loads(profile_path.read_text())
    allowed = raw.get("tg_allowed_ids", [])
    removed = []
    not_found = []
    for tid in tg_ids:
        if tid in allowed:
            allowed.remove(tid)
            removed.append(tid)
        else:
            not_found.append(tid)
    raw["tg_allowed_ids"] = allowed
    profile_path.write_text(json.dumps(raw, indent=2) + "\n")
    if removed:
        typer.echo(f"revoked: {', '.join(str(t) for t in removed)}")
    for tid in not_found:
        typer.echo(f"{tid} not found in authorized list")


@telegram_app.command("list")
def telegram_list() -> None:
    """List authorized Telegram users."""
    profile_path = CONFIG_DIR / "profile.json"
    if not profile_path.exists():
        typer.echo("error: profile.json not found", err=True)
        raise typer.Exit(code=2)
    import json
    raw = json.loads(profile_path.read_text())
    allowed = raw.get("tg_allowed_ids", [])
    if not allowed:
        typer.echo("no authorized telegram users")
        return
    for tid in allowed:
        typer.echo(str(tid))


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
