"""Constants for the BC Parks GoingToCamp API.

Validated by the prior investigation in this directory (test-report.md).
All IDs are large negative ints by GoingToCamp convention.
"""
from datetime import date
from pathlib import Path

BASE_URL = "https://camping.bcparks.ca"
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)
HTTP_TIMEOUT = 30.0

CAMP_SITE = -2147483648
OVERFLOW_SITE = -2147483647
GROUP_SITE = -2147483643
CAMP_CATEGORY_IDS = (CAMP_SITE, OVERFLOW_SITE, GROUP_SITE)

NON_GROUP_EQUIPMENT = -32768

AVAILABILITY_AVAILABLE = 0
AVAILABILITY_RESERVED = 1
AVAILABILITY_CLOSED = 2
AVAILABILITY_WALK_IN = 3

CONFIG_DIR = Path.home() / ".campcli"
DB_PATH = CONFIG_DIR / "state.db"
CATALOG_PATH = CONFIG_DIR / "catalog.json"
DRIVE_TIMES_PATH = CONFIG_DIR / "drive_times.json"
PROFILE_PATH = CONFIG_DIR / "profile.json"

# BC Parks system rule: reservations open only N months before start date.
# Hard limit set by BC Parks — not user-configurable.
BOOKING_WINDOW_MONTHS = 3


def max_bookable_start(today: date | None = None) -> date:
    """Last start date bookable under BC Parks window (BOOKING_WINDOW_MONTHS).

    Calendar-month math: Jan 4 → Apr 4. If resulting day exceeds month
    length (e.g. Jan 31 → Apr 30), clamps to last day of month.
    """
    if today is None:
        today = date.today()
    total = today.month - 1 + BOOKING_WINDOW_MONTHS  # 0-indexed
    year = today.year + total // 12
    month = total % 12 + 1
    # Clamp day to month length.
    if month == 12:
        dim = 31
    else:
        dim = (date(year, month + 1, 1) - date(year, month, 1)).days
    day = min(today.day, dim)
    return date(year, month, day)


# Home: 3310 Lancaster Ct, Coquitlam, BC
HOME_LATLON = (49.2970917, -122.7658634)


# Pricing seasons. Peak: Jun 15 through Labour Day (first Mon of September).
# Outside that range counts as shoulder/off-season.
PEAK_START_MONTH_DAY = (6, 15)


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
