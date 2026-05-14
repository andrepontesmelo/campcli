"""Read-only view over geocoded drive durations from HOME to each park.

The seam for drive-time data: Application and Presentation receive this
value object instead of reaching into the JSON cache. `load_cache()` is
the only producer and is called only by the composition root.
"""

from __future__ import annotations


class DriveTimes:
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
