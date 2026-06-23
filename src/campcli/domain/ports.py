"""Domain port: BCParksApi Protocol + error types + Repo Protocols + Clock.

This is the seam that inverts the Application → Infrastructure dependency.
Application code depends on this Protocol; Infrastructure (api.py) satisfies it.
Repo Protocols let Application use-case functions express exact I/O needs.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Protocol

from pydantic import BaseModel

from .models import BlockedPark, Booking, Map, Park, Watch


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


# ----- Repo Protocols --------------------------------------------------------

class WatchRepo(Protocol):
    """Persistent storage for Watch domain objects."""

    def add_watch(self, watch: Watch) -> Watch:
        """Persist a new Watch; returns it with id populated."""

    def list_watches(self) -> list[Watch]:
        """Return all watches, ordered by id."""

    def remove_watch(self, watch_id: int) -> bool:
        """Delete a watch by id. Returns True if a row was removed."""


class BookingRepo(Protocol):
    """Persistent storage for Booking domain objects."""

    def add_booking(self, booking: Booking) -> Booking:
        """Persist a new Booking; returns it with id populated."""

    def list_bookings(self) -> list[Booking]:
        """Return all bookings, ordered by start_date."""

    def remove_booking(self, booking_id: int) -> bool:
        """Delete a booking by id. Returns True if a row was removed."""


class BlockedParkRepo(Protocol):
    """Persistent storage for blocked (undesired) parks."""

    def add_blocked(self, blocked: BlockedPark) -> BlockedPark:
        """Persist a blocked park (INSERT OR REPLACE)."""

    def list_blocked(self) -> list[BlockedPark]:
        """Return all blocked parks, ordered by park_name."""

    def remove_blocked(self, park_id: int) -> bool:
        """Unblock a park by id. Returns True if a row was removed."""


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


class BotCommand(BaseModel):
    """A command registered via setMyCommands."""
    command: str
    description: str


class Telegram(Protocol):
    """Transport for Telegram bot I/O.

    All methods may raise arbitrary network exceptions. Implementations are
    responsible for JSON parsing and chat_id filtering.
    """

    def send_to(self, chat_id: str, text: str) -> None:
        """Post a message to the given chat."""

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

