"""Constants for the BC Parks GoingToCamp API.

Validated by the prior investigation in this directory (test-report.md).
All IDs are large negative ints by GoingToCamp convention.
"""
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
