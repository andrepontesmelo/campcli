"""Profile CLI sub-commands (profile *, not-interested *)."""

from __future__ import annotations

import typer

from .. import cli as _cli

profile_app = typer.Typer(no_args_is_help=True, help="Manage search profiles.")
not_interested_app = typer.Typer(
    no_args_is_help=True, help="Manage not-interested entries (parks+dates to skip)."
)
profile_app.add_typer(not_interested_app, name="not-interested")


# ----- profile create ---------------------------------------------------------


@profile_app.command("create")
def profile_create(
    name: str = typer.Argument(..., help="Unique profile name."),
) -> None:
    """Create a new search profile with interactive prompts."""
    _cli.profile_create_uc(_cli._store(), name)


# ----- profile list -----------------------------------------------------------


@profile_app.command("list")
def profile_list() -> None:
    """List all profiles with key fields."""
    _cli.profile_list_uc(_cli._store())


# ----- profile show -----------------------------------------------------------


@profile_app.command("show")
def profile_show(
    name: str = typer.Argument(..., help="Profile name."),
) -> None:
    """Show full profile details."""
    _cli.profile_show_uc(_cli._store(), name)


# ----- profile search ---------------------------------------------------------


@profile_app.command("search")
def profile_search(
    name: str = typer.Argument(..., help="Profile name."),
    months: int | None = typer.Option(
        None, "--months", help="Override profile horizon (months)."
    ),
    distance: str | None = typer.Option(
        None,
        "--distance",
        "-d",
        help="Override max drive time (e.g. '4h', '3h30m', '210m').",
    ),
    group_by: str = typer.Option(
        "weekend",
        "--group-by",
        "-g",
        help="Top-level grouping: 'weekend' (default) or 'park'.",
    ),
    with_urls: bool = typer.Option(
        False,
        "--with-urls",
        "-u",
        help="Print a clickable booking deep-link under each match.",
    ),
    limit_parks: int | None = typer.Option(None, "--limit-parks", hidden=True),
) -> None:
    """Search campsites for a named profile (explicit form)."""
    max_drive_hours = _cli._parse_hours_or_exit(distance)
    drive_times = _cli.load_drive_times()
    with _cli.api_call() as api:
        _cli.profile_search_uc(
            _cli._store(),
            api,
            drive_times,
            name,
            months=months,
            max_drive_hours=max_drive_hours,
            group_by=group_by,
            with_urls=with_urls,
            limit_parks=limit_parks,
        )


# ----- profile enable / disable / delete --------------------------------------


@profile_app.command("enable")
def profile_enable(
    name: str = typer.Argument(..., help="Profile name."),
) -> None:
    """Enable a profile."""
    _cli.profile_enable_uc(_cli._store(), name)


@profile_app.command("disable")
def profile_disable(
    name: str = typer.Argument(..., help="Profile name."),
) -> None:
    """Disable a profile."""
    _cli.profile_disable_uc(_cli._store(), name)


@profile_app.command("delete")
def profile_delete(
    name: str = typer.Argument(..., help="Profile name."),
) -> None:
    """Delete a profile permanently."""
    _cli.profile_delete_uc(_cli._store(), name)


# ----- profile tg-* commands --------------------------------------------------


@profile_app.command("tg-add")
def profile_tg_add(
    name: str = typer.Argument(..., help="Profile name."),
    tg_id: int = typer.Argument(..., help="Telegram user ID to authorize."),
) -> None:
    """Add a Telegram user ID to a profile."""
    _cli.profile_tg_add_uc(_cli._store(), name, tg_id)


@profile_app.command("tg-rm")
def profile_tg_rm(
    name: str = typer.Argument(..., help="Profile name."),
    tg_id: int = typer.Argument(..., help="Telegram user ID to remove."),
) -> None:
    """Remove a Telegram user ID from a profile."""
    _cli.profile_tg_rm_uc(_cli._store(), name, tg_id)


@profile_app.command("tg-list")
def profile_tg_list(
    name: str = typer.Argument(..., help="Profile name."),
) -> None:
    """List Telegram user IDs authorized for a profile."""
    _cli.profile_tg_list_uc(_cli._store(), name)


# ----- profile edit -----------------------------------------------------------


@profile_app.command("edit")
def profile_edit(
    name: str = typer.Argument(..., help="Profile name."),
) -> None:
    """Edit a profile interactively — add/remove patterns, parks, Telegram IDs."""
    _cli.profile_edit_uc(_cli._store(), name)


# ----- not-interested ---------------------------------------------------------


@not_interested_app.command("add")
def not_interested_add(
    profile_name: str = typer.Argument(..., help="Profile name."),
    park_name: str = typer.Argument(..., help="Park name."),
    date_start: str = typer.Argument(..., help="Start date (YYYY-MM-DD)."),
    date_end: str = typer.Argument(..., help="End date (YYYY-MM-DD)."),
) -> None:
    """Mark a park+dates as not interested for a profile."""
    store = _cli._store()
    start = _cli._parse_date_or_exit(date_start)
    end = _cli._parse_date_or_exit(date_end)
    with _cli.api_call() as api:
        _cli.not_interested_add_uc(store, store, api, profile_name, park_name, start, end)


@not_interested_app.command("rm")
def not_interested_rm(
    profile_name: str = typer.Argument(..., help="Profile name."),
    park_name: str = typer.Argument(..., help="Park name."),
    date_start: str = typer.Argument(..., help="Start date (YYYY-MM-DD)."),
    date_end: str = typer.Argument(..., help="End date (YYYY-MM-DD)."),
) -> None:
    """Remove a not-interested entry."""
    store = _cli._store()
    start = _cli._parse_date_or_exit(date_start)
    end = _cli._parse_date_or_exit(date_end)
    with _cli.api_call() as api:
        _cli.not_interested_rm_uc(store, store, api, profile_name, park_name, start, end)


@not_interested_app.command("list")
def not_interested_list(
    profile_name: str = typer.Argument(..., help="Profile name."),
) -> None:
    """List not-interested entries for a profile."""
    store = _cli._store()
    with _cli.api_call() as api:
        _cli.not_interested_list_uc(store, store, api, profile_name)
