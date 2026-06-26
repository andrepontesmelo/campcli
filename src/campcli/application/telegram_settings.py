"""Module-level functions for Telegram settings management.

Extracted from ``Poller`` so that settings CRUD is testable without
constructing a full Poller (which needs api, telegram, notifier_factory,
profile_repo, etc.).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..domain.ports import ProfileRepo, SettingsRepo


def get_verbose(settings_repo: SettingsRepo, tg_id: int) -> bool:
    """Return True if verbose logging is enabled for *tg_id*."""
    val = settings_repo.get_setting(f"verbose:{tg_id}")
    return val == "on"


def set_verbose(settings_repo: SettingsRepo, tg_id: int, on: bool) -> None:
    """Persist the verbose logging preference for *tg_id*."""
    settings_repo.set_setting(f"verbose:{tg_id}", "on" if on else "off")


def get_chat_id(settings_repo: SettingsRepo, tg_id: int) -> str | None:
    """Return the last-seen chat_id for *tg_id*, or None."""
    return settings_repo.get_setting(f"chat:{tg_id}")


def set_chat_id(settings_repo: SettingsRepo, tg_id: int, chat_id: str) -> None:
    """Persist the last-seen chat_id for *tg_id*."""
    settings_repo.set_setting(f"chat:{tg_id}", chat_id)


def refresh_tg_allowed_ids(profile_repo: ProfileRepo) -> list[int]:
    """Return a sorted union of ``tg_allowed_ids`` across enabled profiles.

    This is the authoritative computation; callers should store the result
    rather than calling this on every access.
    """
    profiles = profile_repo.list_enabled()
    ids: set[int] = set()
    for p in profiles:
        ids.update(p.tg_allowed_ids)
    return sorted(ids)
