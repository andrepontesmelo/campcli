"""BC Parks booking window — start dates are bookable only N months ahead."""
from __future__ import annotations

from datetime import date

BOOKING_WINDOW_MONTHS = 3


def max_bookable_start(today: date | None = None) -> date:
    """Last start date bookable under BC Parks window (BOOKING_WINDOW_MONTHS).

    Calendar-month math: Jan 4 → Apr 4. If resulting day exceeds month
    length (e.g. Jan 31 → Apr 30), clamps to last day of month.
    """
    if today is None:
        today = date.today()
    total = today.month - 1 + BOOKING_WINDOW_MONTHS
    year = today.year + total // 12
    month = total % 12 + 1
    if month == 12:
        dim = 31
    else:
        dim = (date(year, month + 1, 1) - date(year, month, 1)).days
    day = min(today.day, dim)
    return date(year, month, day)
