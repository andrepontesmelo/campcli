from __future__ import annotations

import re
from dataclasses import dataclass
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
# Pattern spec — parsed search pattern
# ---------------------------------------------------------------------------


class PatternSpec(NamedTuple):
    """A parsed search pattern — weekday, span, min/max nights."""

    weekday: int
    span_nights: int
    min_nights: int
    max_nights: int


_WEEKDAYS: dict[str, int] = {
    "mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6,
}


def parse_pattern(s: str) -> PatternSpec:
    """Parse ``"fri-sun"`` → ``(4, 2, 2, 2)`` or ``"fri-mon:2-3"`` → ``(4, 3, 2, 3)``.

    Returns ``(start_weekday, span_nights, min_nights, max_nights)``.
    Raises ``ValueError`` for invalid patterns.
    """
    # Extract optional :min-max suffix.
    suffix: str | None = None
    if ":" in s:
        s_part, suffix_str = s.split(":", 1)
        suffix = suffix_str
    else:
        s_part = s

    parts = s_part.split("-")
    if len(parts) != 2:
        raise ValueError(
            f"invalid pattern {s!r}: expected 'day-day' format "
            f"(e.g. 'fri-sun')"
        )
    start_str, end_str = parts
    start = _WEEKDAYS.get(start_str.lower())
    end = _WEEKDAYS.get(end_str.lower())
    if start is None:
        raise ValueError(
            f"invalid pattern {s!r}: unknown day {start_str!r} "
            f"(expected mon/tue/wed/thu/fri/sat/sun)"
        )
    if end is None:
        raise ValueError(
            f"invalid pattern {s!r}: unknown day {end_str!r} "
            f"(expected mon/tue/wed/thu/fri/sat/sun)"
        )
    if end == start:
        raise ValueError(
            f"invalid pattern {s!r}: end day {end_str} must come after "
            f"start day {start_str} (same-day pattern)"
        )
    span_nights = (end - start) % 7
    if span_nights > 5:
        raise ValueError(
            f"invalid pattern {s!r}: span too long — {span_nights} nights "
            f"exceeds maximum of 5 (week-wrap not allowed)"
        )

    if suffix is not None:
        mm = re.fullmatch(r"(\d+)-(\d+)", suffix)
        if mm is None:
            raise ValueError(
                f"invalid pattern {s!r}: malformed min-max suffix "
                f"{suffix!r} (expected format like '2-3')"
            )
        min_nights = int(mm.group(1))
        max_nights = int(mm.group(2))
        if min_nights < 1:
            raise ValueError(
                f"invalid pattern {s!r}: min_nights ({min_nights}) "
                f"must be >= 1"
            )
        if min_nights > max_nights:
            raise ValueError(
                f"invalid pattern {s!r}: min_nights ({min_nights}) "
                f"must be <= max_nights ({max_nights})"
            )
        if max_nights > span_nights:
            raise ValueError(
                f"invalid pattern {s!r}: max_nights ({max_nights}) "
                f"exceeds span_nights ({span_nights})"
            )
    else:
        min_nights = max_nights = span_nights

    return PatternSpec(start, span_nights, min_nights, max_nights)


# ---------------------------------------------------------------------------
# Park query — a (park, optional map) filter for a profile
# ---------------------------------------------------------------------------


class ParkQuery(NamedTuple):
    """A (park, optional map) query filter for a profile.

    ``park_query`` is a park name or partial match string.
    ``map_query`` is an optional map (sub-area) name filter.
    """

    park_query: str
    map_query: str | None = None


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
    patterns: list[PatternSpec] = Field(default_factory=list)
    parks: list[ParkQuery] = Field(default_factory=list)
    tg_allowed_ids: list[int] = Field(default_factory=list)


@dataclass(frozen=True)
class NotInterested:
    profile_id: int
    park_id: int
    date_start: date
    date_end: date


# ---------------------------------------------------------------------------
# DriveTimes — value object over geocoded driving durations
# ---------------------------------------------------------------------------


class DriveTimes:
    """Read-only view over geocoded drive durations from HOME to each park.

    The seam for drive-time data: Application and Presentation receive this
    value object instead of reaching into the JSON cache.  ``empty()`` is
    the only producer accessible outside the infrastructure layer.
    """

    def __init__(self, entries: dict[int, dict]) -> None:
        self._entries = entries

    @classmethod
    def empty(cls) -> "DriveTimes":
        return cls({})

    def hours_for(self, park_id: int) -> float | None:
        entry = self._entries.get(park_id)
        return entry.get("hours") if entry else None

    def is_within(self, park_id: int, max_hours: float) -> bool:
        h = self.hours_for(park_id)
        return h is not None and h <= max_hours

    def __bool__(self) -> bool:
        return bool(self._entries)



