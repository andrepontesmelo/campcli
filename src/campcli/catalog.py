"""Park and map lookup with on-disk JSON cache.

The park list rarely changes — we cache it in ~/.campcli/catalog.json so
repeated CLI invocations don't re-fetch ~111 parks.
"""
from __future__ import annotations

import json
from pathlib import Path

from .api import BCParksClient
from .constants import CAMP_CATEGORY_IDS, CATALOG_PATH, CONFIG_DIR
from .models import Map, Park


def _localized_name(loc: dict) -> str:
    values = loc.get("localizedValues") or [{}]
    v = values[0]
    return v.get("fullName") or v.get("name") or v.get("title") or "?"


def _is_campground(loc: dict) -> bool:
    cats = loc.get("resourceCategoryIds") or []
    return any(c in cats for c in CAMP_CATEGORY_IDS)


def fetch_parks(client: BCParksClient) -> list[Park]:
    locations = client.list_resource_locations()
    parks = [
        Park(
            park_id=loc["resourceLocationId"],
            name=_localized_name(loc),
            region=loc.get("region") or None,
        )
        for loc in locations
        if _is_campground(loc)
    ]
    parks.sort(key=lambda p: p.name)
    return parks


def fetch_maps(client: BCParksClient, park_id: int) -> list[Map]:
    raw = client.list_maps_for_park(park_id)
    maps = [
        Map(
            map_id=m["mapId"],
            park_id=park_id,
            name=_localized_name(m),
        )
        for m in raw
        if m.get("mapId") is not None
    ]
    maps.sort(key=lambda m: m.name)
    return maps


def load_cached_parks() -> list[Park] | None:
    if not CATALOG_PATH.exists():
        return None
    data = json.loads(CATALOG_PATH.read_text())
    return [Park(**p) for p in data]


def save_cached_parks(parks: list[Park]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CATALOG_PATH.write_text(
        json.dumps([p.model_dump() for p in parks], indent=2)
    )


def get_parks(client: BCParksClient, refresh: bool = False) -> list[Park]:
    if not refresh:
        cached = load_cached_parks()
        if cached is not None:
            return cached
    parks = fetch_parks(client)
    save_cached_parks(parks)
    return parks


def find_park(parks: list[Park], park_id: int) -> Park | None:
    return next((p for p in parks if p.park_id == park_id), None)
