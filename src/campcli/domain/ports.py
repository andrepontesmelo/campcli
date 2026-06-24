"""Domain port: BCParksApi Protocol + error types + repo protocols + Clock.

This is the seam that inverts the Application → Infrastructure dependency.
Application code depends on this Protocol; Infrastructure (api.py) satisfies it.
Repo Protocols let Application use-case functions express exact I/O needs.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Protocol

from pydantic import BaseModel

from .models import Map, NotInterested, Park, ParkQuery, PatternSpec, Profile


class ApiError(RuntimeError):
    pass


class RateLimited(ApiError):
    pass


class BCParksApi(Protocol):
    """Source of BC Parks catalog + availability data.

    All methods may raise ApiError (network/HTTP errors) or RateLimited
    (HTTP 403/429). Implementations are responsible for JSON parsing — return
    values are Domain objects or structured primitives, never raw API dicts.
    """

    def list_parks(self, *, refresh: bool = False) -> list[Park]:
        """Return all campground parks, optionally forcing a cache refresh."""

    def list_maps(self, park_id: int) -> list[Map]:
        """Return maps (sub-areas) for a park."""

    def map_availability(
        self,
        *,
        park_id: int,
        map_id: int,
        start: date,
        end: date,
        party_size: int = 1,
    ) -> dict[int, list[dict[str, Any]]]:
        """Return {site_id: [slot dicts]} for a map+date range.

        Caller decides the availability rule (e.g. all slots == AVAILABLE).
        """

    def resource_details(self, *, park_id: int, map_id: int) -> Any:
        """Fetch map/resource details for fee extraction."""


class SettingsRepo(Protocol):
    """Generic key/value settings storage."""

    def get_setting(self, key: str) -> str | None:
        """Return value for key, or None if unset."""

    def set_setting(self, key: str, value: str) -> None:
        """Upsert a key/value pair."""


# ----- Clock port ------------------------------------------------------------

class Clock(Protocol):
    """Source of wall-clock time for timestamping Domain objects."""

    def now(self) -> datetime:
        """Return the current datetime."""


# ----- Telegram port ---------------------------------------------------------

class TelegramUpdate(BaseModel):
    update_id: int
    chat_id: str
    text: str
    from_id: int | None = None
    callback_query_id: str | None = None
    callback_data: str | None = None
    message_id: int | None = None
    reply_to_message_id: int | None = None


class BotCommand(BaseModel):
    """A command registered via setMyCommands."""
    command: str
    description: str


class Telegram(Protocol):
    """Transport for Telegram bot I/O.

    All methods may raise arbitrary network exceptions. Implementations are
    responsible for JSON parsing and chat_id filtering.
    """

    def send_to(self, chat_id: str, text: str) -> int:
        """Post a message to the given chat. Returns the Telegram message_id."""

    def poll_updates(
        self, offset: int | None = None, long_poll_timeout: int = 0
    ) -> list[TelegramUpdate]:
        """Poll Telegram for incoming commands. Returns [] on error."""

    def set_my_commands(self, commands: list[BotCommand]) -> None:
        """Register bot commands (auto-complete in chat UI)."""

    def send_inline_keyboard(
        self, chat_id: str, text: str, buttons: list[list[dict[str, str]]]
    ) -> int:
        """Send a message with inline keyboard; return message_id."""

    def edit_message_reply_markup(
        self,
        chat_id: str,
        message_id: int,
        text: str | None = None,
        buttons: list[list[dict[str, str]]] | None = None,
    ) -> None:
        """Edit an existing message's reply markup."""

    def answer_callback_query(self, query_id: str, text: str | None = None) -> None:
        """Acknowledge a callback query (dismisses loading spinner)."""


class ProfileRepo(Protocol):
    """Repository for managing search profiles.

    Each profile is a named, independently-enabled search configuration.
    Child data (patterns, parks, telegram IDs) is stored in sibling tables
    and resolved by the repository.
    """

    def create(self, profile: Profile) -> Profile:
        """Insert a new profile. Assigns id, created_at, updated_at."""

    def list_all(self) -> list[Profile]:
        """Return every profile (enabled and disabled)."""

    def list_enabled(self) -> list[Profile]:
        """Return only enabled profiles."""

    def get_by_name(self, name: str) -> Profile | None:
        """Look up a profile by unique name. Returns None if not found."""

    def get_by_id(self, profile_id: int) -> Profile | None:
        """Look up a profile by id. Returns None if not found."""

    def update(self, profile: Profile) -> Profile:
        """Persist all fields of an existing profile. Bumps updated_at."""

    def delete(self, name: str) -> bool:
        """Remove a profile by name. Returns True if a row was deleted."""

    def set_enabled(self, name: str, enabled: bool) -> bool:
        """Toggle the enabled flag. Returns True if the profile exists."""

    # ---- child CRUD -------------------------------------------------------

    def add_pattern(self, profile_name: str, pattern: str, sort_order: int = 0) -> None:
        """Add a pattern to a profile. Raises KeyError if profile not found."""

    def remove_pattern(self, profile_name: str, pattern: str) -> bool:
        """Remove a pattern from a profile. Returns True if a row was deleted."""

    def list_patterns(self, profile_name: str) -> list[PatternSpec]:
        """Return patterns for a profile (sorted by sort_order)."""

    def add_park(self, profile_name: str, park_query: str, map_query: str | None = None) -> None:
        """Add a park query to a profile. Raises KeyError if profile not found."""

    def remove_park(self, profile_name: str, park_query: str) -> bool:
        """Remove a park query from a profile. Returns True if a row was deleted."""

    def list_parks(self, profile_name: str) -> list[ParkQuery]:
        """Return park queries for a profile."""

    def add_tg_id(self, profile_name: str, tg_id: int) -> None:
        """Add a Telegram ID to a profile. Raises KeyError if profile not found."""

    def remove_tg_id(self, profile_name: str, tg_id: int) -> bool:
        """Remove a Telegram ID from a profile. Returns True if a row was deleted."""

    def list_tg_ids(self, profile_name: str) -> list[int]:
        """Return Telegram IDs for a profile."""


class NotInterestedRepo(Protocol):
    """Repository for NotInterested profile-level skip preferences.

    Each entry says: "for this Profile, do not suggest this Park on this
    specific date range again." Scoped by (profile_id, park_id, date_start,
    date_end).
    """

    def add(
        self, profile_id: int, park_id: int, date_start: date, date_end: date
    ) -> None:
        """Record a not-interested entry. Raises ValueError on duplicate."""

    def remove(
        self, profile_id: int, park_id: int, date_start: date, date_end: date
    ) -> None:
        """Remove a not-interested entry. No-op if not found."""

    def list_for(self, profile_id: int) -> list[NotInterested]:
        """Return all not-interested entries for a profile."""

    def load_skip_set(self, profile_id: int) -> set[tuple[int, date, date]]:
        """Return {(park_id, date_start, date_end)} for O(1) lookup during notify."""

    def record_sent(
        self, message_id: int, profile_id: int, park_id: int, date_start: date, date_end: date
    ) -> None:
        """Record that a notification was sent (maps message_id to park+dates)."""

    def lookup_sent(
        self, message_id: int
    ) -> tuple[int, int, date, date] | None:
        """Look up (profile_id, park_id, date_start, date_end) for a sent message_id."""

