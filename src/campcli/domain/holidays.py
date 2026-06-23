"""BC statutory holidays — calendar + nearest-holiday lookup."""
from __future__ import annotations

from datetime import date

HOLIDAY_NEAR_DAYS = 3

HOLIDAYS: list[tuple[date, str]] = [
    (date(2026, 1, 1), "New Year's Day"),
    (date(2026, 2, 16), "Family Day"),
    (date(2026, 4, 3), "Good Friday"),
    (date(2026, 5, 18), "Victoria Day"),
    (date(2026, 7, 1), "Canada Day"),
    (date(2026, 8, 3), "BC Day"),
    (date(2026, 9, 7), "Labour Day"),
    (date(2026, 9, 30), "Truth and Reconciliation"),
    (date(2026, 10, 12), "Thanksgiving Day"),
    (date(2026, 11, 11), "Remembrance Day"),
    (date(2026, 12, 25), "Christmas Day"),
    (date(2026, 12, 28), "Boxing Day"),
    (date(2027, 1, 1), "New Year's Day"),
    (date(2027, 2, 15), "Family Day"),
    (date(2027, 3, 26), "Good Friday"),
    (date(2027, 5, 24), "Victoria Day"),
    (date(2027, 7, 1), "Canada Day"),
    (date(2027, 8, 2), "BC Day"),
    (date(2027, 9, 6), "Labour Day"),
    (date(2027, 9, 30), "Truth and Reconciliation"),
    (date(2027, 10, 11), "Thanksgiving Day"),
    (date(2027, 11, 11), "Remembrance Day"),
    (date(2027, 12, 27), "Christmas Day"),
    (date(2027, 12, 28), "Boxing Day"),
]


def nearest_holiday(start: date, end: date) -> tuple[date, str] | None:
    """Return (date, name) of the closest holiday within HOLIDAY_NEAR_DAYS of [start, end], else None."""
    best: tuple[int, date, str] | None = None
    for h_date, h_name in HOLIDAYS:
        if start <= h_date <= end:
            dist = 0
        else:
            dist = min(abs((h_date - start).days), abs((h_date - end).days))
        if dist <= HOLIDAY_NEAR_DAYS and (best is None or dist < best[0]):
            best = (dist, h_date, h_name)
    if best is None:
        return None
    return best[1], best[2]
