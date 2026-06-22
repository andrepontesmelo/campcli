"""Profile model and loader for search preferences.

Application layer per ADR-0010. The Profile Pydantic model holds
user-configurable search preferences loaded from ~/.campcli/profile.json.

On first use the file is generated with defaults. Human-friendly pattern
notation (``fri-sun``) is parsed into (weekday, nights) tuples at load time.
Park/map allowlist names are resolved against the BC Parks catalog at load time.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from ..constants import CONFIG_DIR, PROFILE_PATH

if TYPE_CHECKING:
    from ..domain.models import Map, Park
    from ..domain.ports import BCParksApi

# ---------------------------------------------------------------------------
# Pattern parsing
# ---------------------------------------------------------------------------

_WEEKDAYS: dict[str, int] = {
    "mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6,
}


def parse_pattern(s: str) -> tuple[int, int]:
    """Parse ``"fri-sun"`` → ``(4, 3)``.

    Returns ``(start_weekday, nights)``. Raises ``ValueError`` for
    unknown day names or wrap-around patterns.
    """
    parts = s.split("-")
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
    if end < start:
        raise ValueError(
            f"invalid pattern {s!r}: end day {end_str} is before "
            f"start day {start_str} (no wrap-around)"
        )
    nights = end - start + 1
    return start, nights


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class AllowedEntry(BaseModel):
    """A single park (and optional map) in the allowlist."""

    park: str
    map: str | None = None


class Profile(BaseModel):
    """Search preferences, loaded from or saved to ``profile.json``.

    Fields mirror the JSON schema. ``allowed_park_ids`` is populated at
    load time by resolving park/map names — it is not serialized.
    """

    model_config = {"extra": "forbid"}

    patterns: list[str] = Field(default_factory=lambda: ["fri-sun"])
    max_horizon_months: int = 3
    max_drive_hours: float = 3.0
    min_start_date: str | None = None
    rest_days_between_bookings: int = 14
    tg_allowed_ids: list[int] = Field(default_factory=list)
    allowed: list[AllowedEntry] = Field(default_factory=list)
    allowed_park_ids: dict[int, set[int] | None] = Field(
        default_factory=dict,
    )

    # ---- derived helpers ---------------------------------------------------

    def pattern_tuples(self) -> list[tuple[int, int]]:
        """Return patterns as ``[(weekday, nights), …]``."""
        return [parse_pattern(p) for p in self.patterns]

    def min_start_date_parsed(self) -> date | None:
        """Return ``min_start_date`` as a ``date`` or ``None``."""
        if self.min_start_date is None:
            return None
        return date.fromisoformat(self.min_start_date)


# ---------------------------------------------------------------------------
# Profile loader
# ---------------------------------------------------------------------------

_DEFAULT_JSON = {
    "patterns": ["fri-sun"],
    "max_horizon_months": 3,
    "max_drive_hours": 3.0,
    "min_start_date": None,
    "rest_days_between_bookings": 14,
    "tg_allowed_ids": [],
    "allowed": [],
}


def _make_default_profile(path: Path) -> Profile:
    """Write default ``profile.json`` and return it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_DEFAULT_JSON, indent=2) + "\n")
    return Profile()


def _resolve_park(query: str, parks: list[Park]) -> Park:
    """Find a park by name — exact then substring (case-insensitive)."""
    q = query.strip().lower()
    exact = [p for p in parks if p.name.lower() == q]
    if len(exact) == 1:
        return exact[0]
    matches = [p for p in parks if q in p.name.lower()]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise ValueError(f"unknown park {query!r} in allowed list")
    names = ", ".join(p.name for p in matches[:5])
    more = f" (+{len(matches) - 5} more)" if len(matches) > 5 else ""
    raise ValueError(
        f"ambiguous park {query!r} in allowed list: matches {names}{more}"
    )


def _resolve_map(query: str, maps: list[Map]) -> int:
    """Find a map by name (case-insensitive exact match)."""
    matches = [m for m in maps if m.name.lower() == query.lower()]
    if len(matches) == 1:
        return matches[0].map_id
    if not matches:
        raise ValueError(
            f"unknown map {query!r} in allowed list"
        )
    raise ValueError(
        f"ambiguous map {query!r} in allowed list: "
        f"matches {', '.join(m.name for m in matches[:5])}"
    )


def load_profile(api: BCParksApi) -> Profile:
    """Load ``profile.json`` from ``~/.campcli/``, validating and resolving.

    If the file does not exist a default is generated and written to disk
    before loading.  ``allowed`` entries are resolved against the live park
    catalog — unknown names produce an error at load time (fail-fast).

    Raises ``ValueError`` for schema violations, invalid patterns,
    or unresolvable park/map names.
    """
    path = PROFILE_PATH

    if not path.exists():
        return _make_default_profile(path)

    raw = path.read_text()
    try:
        profile = Profile.model_validate_json(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"profile.json is not valid JSON: {exc}"
        ) from exc
    except ValueError as exc:
        # Pydantic validation errors come through ValidationError which is
        # a subclass of ValueError.
        raise

    # Validate patterns up front.
    for p in profile.patterns:
        parse_pattern(p)  # raises ValueError on bad pattern

    # Resolve allowed park/map names.
    if profile.allowed:
        parks = api.list_parks()
        resolved: dict[int, set[int] | None] = {}
        for entry in profile.allowed:
            park = _resolve_park(entry.park, parks)
            if entry.map is not None:
                maps = api.list_maps(park.park_id)
                map_id = _resolve_map(entry.map, maps)
                if park.park_id in resolved:
                    existing = resolved[park.park_id]
                    if existing is not None:
                        existing.add(map_id)
                    # existing is None → all maps, keep it.
                else:
                    resolved[park.park_id] = {map_id}
            else:
                resolved[park.park_id] = None  # all maps
        profile.allowed_park_ids = resolved

    return profile
