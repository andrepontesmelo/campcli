"""Profile use-case functions — profile CRUD, resolution, and search.

Extracted from composition/cli.py following ADR-0005 (group by Domain noun).
Each function accepts Protocol ports as parameters (duck-typed per ADR-0001/0004).
"""
from __future__ import annotations

from datetime import date

import typer

from ..application.catalog import resolve_profile_parks
from ..application.search import _search_for_profile
from ..domain.models import DriveTimes, PatternSpec, Profile
from ..domain.ports import BCParksApi, ProfileRepo
from ..presentation import format as fmt
from ._helpers import _confirm_profile_exists


# ----- helpers ----------------------------------------------------------------


def _pattern_to_raw(p: PatternSpec) -> str:
    """Reverse a PatternSpec back to its pattern string."""
    days = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    start = days[p.weekday]
    end = days[(p.weekday + p.span_nights) % 7]
    base = f"{start}-{end}"
    if p.min_nights != p.max_nights or p.min_nights != p.span_nights:
        return f"{base}:{p.min_nights}-{p.max_nights}"
    return base


# ----- profile resolution -----------------------------------------------------


def resolve_profile(
    profile_repo: ProfileRepo,
    requested: str | None,
) -> Profile:
    """Resolve the active profile for a CLI invocation.

    - requested is given (via --profile): use it if it exists and is enabled; error otherwise.
    - requested is None: count enabled profiles.
      - 0: error 'no enabled profiles found; create one with ``campcli profile create <name>``'
      - 1: auto-select that profile.
      - 2+: error 'multiple enabled profiles; specify --profile <name>'.

    Returns the resolved Profile.
    Raises typer.Exit on error.
    """
    if requested is not None:
        profile = profile_repo.get_by_name(requested)
        if profile is None:
            typer.echo(f"error: profile {requested!r} not found", err=True)
            raise typer.Exit(code=2)
        if not profile.enabled:
            typer.echo(f"error: profile {requested!r} is disabled", err=True)
            raise typer.Exit(code=2)
        return profile

    enabled = profile_repo.list_enabled()
    if len(enabled) == 0:
        typer.echo(
            "error: no enabled profiles found; "
            "create one with `campcli profile create <name>`",
            err=True,
        )
        raise typer.Exit(code=2)
    if len(enabled) > 1:
        typer.echo(
            "error: multiple enabled profiles found; specify --profile <name>",
            err=True,
        )
        raise typer.Exit(code=2)
    # Exactly one enabled profile.
    return enabled[0]


# ----- CRUD commands ----------------------------------------------------------


def profile_create(profile_repo: ProfileRepo, name: str) -> None:
    """Create a new search profile with interactive prompts."""
    if profile_repo.get_by_name(name) is not None:
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

    profile = Profile(
        name=name,
        max_horizon_months=max_horizon_months,
        max_drive_hours=max_drive_hours,
        min_start_date=min_start_date,
        rest_days_between_bookings=rest_days,
    )
    created = profile_repo.create(profile)
    typer.echo(f"profile {name!r} created (id={created.id})")

    # Interactive prompts for child rows.
    from ..domain.models import parse_pattern

    typer.echo("")
    typer.echo("Add patterns (one per line, blank to finish):")
    while True:
        raw = typer.prompt("Pattern", default="", show_default=False)
        if not raw:
            break
        try:
            parse_pattern(raw)  # validate before inserting
        except ValueError as e:
            typer.echo(f"  (skipped: {e})", err=True)
            continue
        sort = len(profile_repo.list_patterns(name))
        profile_repo.add_pattern(name, raw, sort_order=sort)

    typer.echo("")
    typer.echo("Add park filters (one per line, blank to finish):")
    while True:
        park = typer.prompt("Park name", default="", show_default=False)
        if not park:
            break
        map_q = typer.prompt("Map name (optional)", default="", show_default=False)
        profile_repo.add_park(name, park, map_q.strip() or None)

    typer.echo("")
    typer.echo("Add Telegram user IDs (one per line, blank to finish):")
    while True:
        raw = typer.prompt("Telegram ID", default="", show_default=False)
        if not raw:
            break
        try:
            profile_repo.add_tg_id(name, int(raw))
        except ValueError:
            typer.echo(f"  (skipped: {raw!r} is not a number)", err=True)


def profile_list(profile_repo: ProfileRepo) -> None:
    """List all profiles with key fields."""
    profiles = profile_repo.list_all()
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
            f"{p.max_drive_hours:<9} {p.rest_days_between_bookings:<6} {created}",
        )


def profile_show(profile_repo: ProfileRepo, name: str) -> None:
    """Show full profile details."""
    profile = _confirm_profile_exists(profile_repo, name)
    typer.echo(f"name:                         {profile.name}")
    typer.echo(f"enabled:                      {'yes' if profile.enabled else 'no'}")
    typer.echo(f"max_horizon_months:           {profile.max_horizon_months}")
    typer.echo(f"max_drive_hours:              {profile.max_drive_hours}")
    typer.echo(f"min_start_date:               {profile.min_start_date or '-'}")
    typer.echo(f"rest_days_between_bookings:   {profile.rest_days_between_bookings}")
    typer.echo(f"patterns:                     {[_pattern_to_raw(p) for p in profile.patterns] or '-'}")
    typer.echo(f"parks:                        {[(pq.park_query, pq.map_query) for pq in profile.parks] or '-'}")
    typer.echo(f"tg_allowed_ids:               {profile.tg_allowed_ids or '-'}")
    typer.echo(f"created_at:                   {profile.created_at or '-'}")
    typer.echo(f"updated_at:                   {profile.updated_at or '-'}")


def profile_delete(profile_repo: ProfileRepo, name: str) -> None:
    """Delete a profile permanently."""
    _confirm_profile_exists(profile_repo, name)
    profile_repo.delete(name)
    typer.echo(f"profile {name!r} deleted")


def profile_enable(profile_repo: ProfileRepo, name: str) -> None:
    """Enable a profile."""
    _confirm_profile_exists(profile_repo, name)
    profile_repo.set_enabled(name, True)
    typer.echo(f"profile {name!r} enabled")


def profile_disable(profile_repo: ProfileRepo, name: str) -> None:
    """Disable a profile."""
    _confirm_profile_exists(profile_repo, name)
    profile_repo.set_enabled(name, False)
    typer.echo(f"profile {name!r} disabled")


# ----- profile tg-* commands --------------------------------------------------


def profile_tg_add(profile_repo: ProfileRepo, name: str, tg_id: int) -> None:
    """Add a Telegram user ID to a profile."""
    _confirm_profile_exists(profile_repo, name)
    profile_repo.add_tg_id(name, tg_id)
    typer.echo(f"Telegram ID {tg_id} added to profile {name!r}")


def profile_tg_rm(profile_repo: ProfileRepo, name: str, tg_id: int) -> None:
    """Remove a Telegram user ID from a profile."""
    _confirm_profile_exists(profile_repo, name)
    if profile_repo.remove_tg_id(name, tg_id):
        typer.echo(f"Telegram ID {tg_id} removed from profile {name!r}")
    else:
        typer.echo(f"Telegram ID {tg_id} not found in profile {name!r}", err=True)
        raise typer.Exit(code=2)


def profile_tg_list(profile_repo: ProfileRepo, name: str) -> None:
    """List Telegram user IDs authorized for a profile."""
    _confirm_profile_exists(profile_repo, name)
    ids = profile_repo.list_tg_ids(name)
    if not ids:
        typer.echo(f"no Telegram IDs authorized for profile {name!r}")
        return
    for tid in ids:
        typer.echo(str(tid))


# ----- profile edit -----------------------------------------------------------


def profile_edit(profile_repo: ProfileRepo, name: str) -> None:
    """Edit a profile interactively — add/remove patterns, parks, Telegram IDs."""
    _confirm_profile_exists(profile_repo, name)

    while True:
        # Show current state
        pats = profile_repo.list_patterns(name)
        parks = profile_repo.list_parks(name)
        tg_ids = profile_repo.list_tg_ids(name)
        typer.echo("")
        typer.echo(f"Editing profile {name!r}:")
        for p in pats:
            raw = _pattern_to_raw(p)
            typer.echo(f"  pattern:      {raw}")
        for pq in parks:
            parts = pq.park_query
            if pq.map_query:
                parts = f"{pq.park_query} (map: {pq.map_query})"
            typer.echo(f"  park:         {parts}")
        for tid in tg_ids:
            typer.echo(f"  tg_id:        {tid}")
        typer.echo("")
        typer.echo("What would you like to do?")
        typer.echo("  1) Add a pattern")
        typer.echo("  2) Remove a pattern")
        typer.echo("  3) Add a park")
        typer.echo("  4) Remove a park")
        typer.echo("  5) Add a Telegram ID")
        typer.echo("  6) Remove a Telegram ID")
        typer.echo("  7) Done")

        choice = typer.prompt("Choice", default="7")
        if choice == "1":
            raw = typer.prompt("Pattern (e.g. 'fri-sun' or 'fri-mon:2-3')")
            profile_repo.add_pattern(name, raw)
            typer.echo(f"pattern {raw!r} added")
        elif choice == "2":
            raw = typer.prompt("Pattern to remove")
            if profile_repo.remove_pattern(name, raw):
                typer.echo(f"pattern {raw!r} removed")
            else:
                typer.echo(f"pattern {raw!r} not found", err=True)
        elif choice == "3":
            park = typer.prompt("Park name or query")
            map_q = typer.prompt("Map name (optional)", default="")
            map_q = map_q.strip() or None
            profile_repo.add_park(name, park, map_q)
            typer.echo(f"park {park!r} added")
        elif choice == "4":
            park = typer.prompt("Park query to remove")
            if profile_repo.remove_park(name, park):
                typer.echo(f"park {park!r} removed")
            else:
                typer.echo(f"park {park!r} not found", err=True)
        elif choice == "5":
            tg_id = typer.prompt("Telegram ID", type=int)
            profile_repo.add_tg_id(name, tg_id)
            typer.echo(f"Telegram ID {tg_id} added")
        elif choice == "6":
            tg_id = typer.prompt("Telegram ID", type=int)
            if profile_repo.remove_tg_id(name, tg_id):
                typer.echo(f"Telegram ID {tg_id} removed")
            else:
                typer.echo(f"Telegram ID {tg_id} not found", err=True)
        elif choice == "7":
            typer.echo("done")
            break
        else:
            typer.echo("invalid choice", err=True)


# ----- search ----------------------------------------------------------------


def profile_search(
    profile_repo: ProfileRepo,
    api: BCParksApi,
    drive_times: DriveTimes,
    name: str,
    *,
    months: int | None = None,
    max_drive_hours: float | None = None,
    group_by: str = "weekend",
    with_urls: bool = False,
    limit_parks: int | None = None,
) -> None:
    """Search campsites for a named profile (explicit form)."""
    profile = _confirm_profile_exists(profile_repo, name)
    if not profile.enabled:
        typer.echo(f"error: profile {name!r} is disabled", err=True)
        raise typer.Exit(code=2)
    if group_by not in ("weekend", "park"):
        typer.echo("error: --group-by must be 'weekend' or 'park'", err=True)
        raise typer.Exit(code=1)
    typer.echo(f"Profile: {profile.name}", err=True)
    _search_for_profile(
        profile, api=api, drive_times=drive_times,
        months=months, max_drive_hours=max_drive_hours,
        group_by=group_by, with_urls=with_urls, limit_parks=limit_parks,
    )
