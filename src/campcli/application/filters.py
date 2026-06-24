"""Daemon-side filtering: booking-adjacency suppression.

Pure functions, no I/O. Booking adjacency: at least one weekend of rest
between trips, i.e. ≥14 days between start dates.
"""
from __future__ import annotations

from datetime import date


def gap_days_to_nearest(
    target: date, booking_starts: list[date]
) -> tuple[int | None, int | None]:
    """Return (days_to_prev_booking, days_to_next_booking) from `target`.

    Each value is None if there is no booking on that side.
    """
    prev_gap: int | None = None
    next_gap: int | None = None
    for b in booking_starts:
        delta = (b - target).days
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
    target: date, booking_starts: list[date], rest_days: int = 14
) -> bool:
    """True if any booking start is within `rest_days` of `target` (<, not <=)."""
    return any(abs((b - target).days) < rest_days for b in booking_starts)


# Notification policy (blocked + adjacency + dedup) now lives in
# application/notification_policy.py; these stay as the pure rule primitives.
