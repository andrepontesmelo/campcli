"""Not-interested use-case functions — add, remove, list skip entries per profile.

Extracted from composition/cli.py following ADR-0005 (group by Domain noun).
Each function accepts Protocol ports as parameters (duck-typed per ADR-0001/0004).
"""
from __future__ import annotations

from datetime import date

import typer

from ..application.catalog import resolve_park
from ..domain.ports import BCParksApi, NotInterestedRepo, ProfileRepo


# ----- helpers ----------------------------------------------------------------


def _confirm_profile_exists(profile_repo: ProfileRepo, name: str):
    """Look up a profile by name. Exit with error if not found."""
    profile = profile_repo.get_by_name(name)
    if profile is None:
        typer.echo(f"error: profile {name!r} not found", err=True)
        raise typer.Exit(code=2)
    return profile


# ----- not-interested add -----------------------------------------------------


def not_interested_add(
    not_interested_repo: NotInterestedRepo,
    profile_repo: ProfileRepo,
    api: BCParksApi,
    profile_name: str,
    park_name: str,
    date_start: date,
    date_end: date,
) -> None:
    """Mark a park+dates as not interested for a profile."""
    profile = _confirm_profile_exists(profile_repo, profile_name)
    if date_start > date_end:
        typer.echo("error: date_start must not be after date_end", err=True)
        raise typer.Exit(code=2)
    try:
        park = resolve_park(api, park_name)
    except ValueError as e:
        typer.echo(f"error: {e}", err=True)
        raise typer.Exit(code=2)
    try:
        not_interested_repo.add(profile.id, park.park_id, date_start, date_end)
    except ValueError:
        typer.echo("Already marked not interested.", err=True)
        raise typer.Exit(code=2)
    typer.echo(
        f"Marked {park.name} as not interested ({date_start} – {date_end}) "
        f"for profile {profile_name!r}"
    )


# ----- not-interested rm ------------------------------------------------------


def not_interested_rm(
    not_interested_repo: NotInterestedRepo,
    profile_repo: ProfileRepo,
    api: BCParksApi,
    profile_name: str,
    park_name: str,
    date_start: date,
    date_end: date,
) -> None:
    """Remove a not-interested entry."""
    profile = _confirm_profile_exists(profile_repo, profile_name)
    if date_start > date_end:
        typer.echo("error: date_start must not be after date_end", err=True)
        raise typer.Exit(code=2)
    try:
        park = resolve_park(api, park_name)
    except ValueError as e:
        typer.echo(f"error: {e}", err=True)
        raise typer.Exit(code=2)
    existing = not_interested_repo.list_for(profile.id)
    if not any(
        e.park_id == park.park_id and e.date_start == date_start and e.date_end == date_end
        for e in existing
    ):
        typer.echo("No matching not-interested entry", err=True)
        raise typer.Exit(code=2)
    not_interested_repo.remove(profile.id, park.park_id, date_start, date_end)
    typer.echo(
        f"Removed not-interested: {park.name} ({date_start} – {date_end}) "
        f"for profile {profile_name!r}"
    )


# ----- not-interested list ----------------------------------------------------


def not_interested_list(
    not_interested_repo: NotInterestedRepo,
    profile_repo: ProfileRepo,
    api: BCParksApi,
    profile_name: str,
) -> None:
    """List not-interested entries for a profile."""
    profile = _confirm_profile_exists(profile_repo, profile_name)
    entries = not_interested_repo.list_for(profile.id)
    if not entries:
        typer.echo(f"No not-interested entries for profile {profile_name!r}")
        return
    parks = {p.park_id: p.name for p in api.list_parks()}
    header = f"{'Park':<30} {'Start':<12} {'End':<12}"
    typer.echo(header)
    typer.echo("-" * len(header))
    for e in entries:
        park_name = parks.get(e.park_id, str(e.park_id))
        typer.echo(
            f"{park_name:<30} {e.date_start.isoformat():<12} {e.date_end.isoformat():<12}"
        )
