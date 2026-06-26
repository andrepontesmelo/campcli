"""Shared helper functions used across application modules."""
from __future__ import annotations

import typer

from ..domain.models import Profile
from ..domain.ports import ProfileRepo


def _confirm_profile_exists(profile_repo: ProfileRepo, name: str) -> Profile:
    """Look up a profile by name. Exit with error if not found."""
    profile = profile_repo.get_by_name(name)
    if profile is None:
        typer.echo(f"error: profile {name!r} not found", err=True)
        raise typer.Exit(code=2)
    return profile
