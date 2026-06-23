"""Filesystem paths and shared service config for campcli state.

All layer-specific constants live in their layer (domain/, infrastructure/,
application/). Only values shared across layers stay here. ADR-0010 endorses
this split.
"""
from __future__ import annotations

from pathlib import Path

# Booking site root. Shared: infrastructure/api uses it as API base;
# application/booking_links uses it to build user-facing booking URLs.
BASE_URL = "https://camping.bcparks.ca"

CONFIG_DIR = Path.home() / ".campcli"
DB_PATH = CONFIG_DIR / "state.db"
CATALOG_PATH = CONFIG_DIR / "catalog.json"
DRIVE_TIMES_PATH = CONFIG_DIR / "drive_times.json"
PROFILE_PATH = CONFIG_DIR / "profile.json"
