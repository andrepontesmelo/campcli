"""Domain port: BCParksApi Protocol + error types.

This is the seam that inverts the Application → Infrastructure dependency.
Application code depends on this Protocol; Infrastructure (api.py) satisfies it.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Protocol

from pydantic import BaseModel

from .models import Map, Park


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


# ----- Telegram port ---------------------------------------------------------

class TelegramUpdate(BaseModel):
    update_id: int
    chat_id: str
    text: str


class Telegram(Protocol):
    """Transport for Telegram bot I/O.

    All methods may raise arbitrary network exceptions. Implementations are
    responsible for JSON parsing and chat_id filtering.
    """

    def send(self, text: str) -> None:
        """Post a message to the configured chat."""

    def poll_updates(self, offset: int | None = None) -> list[TelegramUpdate]:
        """Short-poll Telegram for incoming commands. Returns [] on error."""
