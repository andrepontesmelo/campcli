"""Daemon-side filtering: blocked parks + booking-adjacency suppression.

Pure functions, no I/O. Booking adjacency: at least one weekend of rest
between trips, i.e. ≥14 days between start dates.
"""
from __future__ import annotations

from datetime import date

from ..domain.models import Booking, WeekendMatch

REST_DAYS = 14  # min |Δstart_date| between trips (1 weekend off in between)


def gap_days_to_nearest(
    target: date, bookings: list[Booking]
) -> tuple[int | None, int | None]:
    """Return (days_to_prev_booking, days_to_next_booking) from `target`.

    Each value is None if there is no booking on that side.
    """
    prev_gap: int | None = None
    next_gap: int | None = None
    for b in bookings:
        delta = (b.start_date - target).days
        if delta < 0:
            d = -delta
            if prev_gap is None or d < prev_gap:
                prev_gap = d
        elif delta > 0:
            if next_gap is None or delta < next_gap:
                next_gap = delta
        else:
            # Same date — count as both 0.
            prev_gap = 0
            next_gap = 0
    return prev_gap, next_gap


def is_too_close(
    target: date, bookings: list[Booking], rest_days: int = REST_DAYS
) -> bool:
    """True if any booking start is within `rest_days` of `target` (<, not <=)."""
    return any(abs((b.start_date - target).days) < rest_days for b in bookings)


def should_notify(
    match: WeekendMatch,
    *,
    bookings: list[Booking],
    blocked_park_ids: set[int],
) -> bool:
    if match.park_id in blocked_park_ids:
        return False
    if is_too_close(match.start_date, bookings):
        return False
    return True
