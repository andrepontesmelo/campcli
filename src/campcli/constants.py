"""Constants for the BC Parks GoingToCamp API.

Validated by the prior investigation in this directory (test-report.md).
All IDs are large negative ints by GoingToCamp convention.
"""
from calendar import FRIDAY, SATURDAY
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

# Home: 3310 Lancaster Ct, Coquitlam, BC
HOME_LATLON = (49.2970917, -122.7658634)


# Hardcoded user profile (will be configurable later).
# Each pattern is (start_weekday, nights). `calendar.FRIDAY == 4`, `SATURDAY == 5`.
DEFAULT_PROFILE = {
    "name": "weekends",
    "patterns": [
        (FRIDAY, 2),    # Fri -> Sun (preferred)
#        (FRIDAY, 1),    # Fri -> Sat
#        (SATURDAY, 1),  # Sat -> Sun
    ],
    "horizon_months": 3,
    "max_drive_hours": 3.0,
}

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
