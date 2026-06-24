from __future__ import annotations

from datetime import date, datetime
from typing import NamedTuple

from pydantic import BaseModel, Field


class Park(BaseModel):
    park_id: int
    name: str
    region: str | None = None


class Map(BaseModel):
    map_id: int
    park_id: int
    name: str


class AvailableSite(BaseModel):
    park_id: int
    park_name: str
    map_id: int
    map_name: str
    site_id: int
    site_name: str | None = None
    start_date: date
    end_date: date


class WeekendMatch(BaseModel):
    park_id: int
    park_name: str
    map_id: int
    map_name: str
    start_date: date
    end_date: date
    nights: int
    available_count: int
    fee_per_night: float | None = None


# ---------------------------------------------------------------------------
# Temporary stubs — replaced with proper entities from child tables
# in slice 7e85bx3w.
# ---------------------------------------------------------------------------


class PatternSpec(NamedTuple):
    """Placeholder — populated from profile_patterns table (slice 7e85bx3w)."""
    pass


class ParkQuery(NamedTuple):
    """Placeholder — populated from profile_parks table (slice 7e85bx3w)."""
    pass


# ---------------------------------------------------------------------------
# Profile domain entity
# ---------------------------------------------------------------------------


class Profile(BaseModel):
    """A named, independently-enabled search configuration.

    Persisted in the ``profiles`` table. Child rows (patterns, parks,
    Telegram IDs) are resolved from sibling tables by the repository.
    """

    model_config = {"extra": "forbid"}

    id: int | None = None
    name: str
    max_horizon_months: int = 3
    max_drive_hours: float = 3.0
    min_start_date: str | None = None
    rest_days_between_bookings: int = 14
    enabled: bool = True
    created_at: str | None = None
    updated_at: str | None = None
    patterns: list = Field(default_factory=list)
    parks: list = Field(default_factory=list)
    tg_allowed_ids: list[int] = Field(default_factory=list)



