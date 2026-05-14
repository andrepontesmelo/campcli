"""One-off geocode + driving-duration lookup from HOME to each park.

Persists results to ~/.campcli/drive_times.json so the CLI can render a drive
column without hitting the network. Traffic is intentionally ignored — we want
a single fixed duration per park as a decision aid.
"""
from __future__ import annotations

import json
import time

import httpx

from ..application.drive_times import DriveTimes
from ..constants import DRIVE_TIMES_PATH, CONFIG_DIR, HOME_LATLON
from ..domain.models import Park

# Hand-curated fallback coordinates for parks Nominatim can't disambiguate
# (unicode names, generic names, island parks). Source: BC Parks website.
MANUAL_LATLON: dict[str, tuple[float, float]] = {
    "Green Lake Provincial Park": (51.4350, -121.2167),
    "Kootenay Lake Provincial Park": (49.6478, -116.8678),
    "Montague Harbour Marine Park": (48.8939, -123.4083),
    "Okanagan Lake North Provincial Park": (50.0506, -119.7269),
    "Okanagan Lake South Provincial Park": (49.7028, -119.7264),
    "Saysutshun (Newcastle Island Marine) Park": (49.1806, -123.9319),
    "Tā Ch'ilā Park [a.k.a. Boya Lake Park]": (59.3603, -129.0922),
    "Wells Gray Provincial Park - Clearwater Lake & Falls Creek": (51.9772, -120.0444),
    "Wells Gray Provincial Park - Mahood Lake": (51.9819, -120.5750),
    "sẁiẁs Provincial Park (Haynes Point)": (49.0264, -119.4517),
}

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OSRM_URL = "https://router.project-osrm.org/route/v1/driving"
USER_AGENT = "campcli/0.1 (drive-times)"
POLITE_DELAY = 1.1  # Nominatim asks for <=1 req/sec


def _geocode(client: httpx.Client, query: str) -> tuple[float, float] | None:
    r = client.get(
        NOMINATIM_URL,
        params={"q": query, "format": "json", "limit": 1, "countrycodes": "ca"},
        headers={"User-Agent": USER_AGENT},
    )
    r.raise_for_status()
    hits = r.json()
    if not hits:
        return None
    return float(hits[0]["lat"]), float(hits[0]["lon"])


def geocode_park(client: httpx.Client, name: str) -> tuple[float, float] | None:
    if name in MANUAL_LATLON:
        return MANUAL_LATLON[name]
    for q in (f"{name}, British Columbia, Canada", f"{name}, BC, Canada"):
        hit = _geocode(client, q)
        if hit is not None:
            return hit
    return None


def route_hours(
    client: httpx.Client, origin: tuple[float, float], dest: tuple[float, float]
) -> float | None:
    lat1, lon1 = origin
    lat2, lon2 = dest
    url = f"{OSRM_URL}/{lon1},{lat1};{lon2},{lat2}"
    r = client.get(url, params={"overview": "false"})
    r.raise_for_status()
    data = r.json()
    routes = data.get("routes") or []
    if not routes:
        return None
    return routes[0]["duration"] / 3600.0


def _load_raw() -> dict[int, dict]:
    if not DRIVE_TIMES_PATH.exists():
        return {}
    raw = json.loads(DRIVE_TIMES_PATH.read_text())
    return {int(k): v for k, v in raw.items()}


def load_cache() -> DriveTimes:
    return DriveTimes(_load_raw())


def save_cache(cache: dict[int, dict]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    DRIVE_TIMES_PATH.write_text(
        json.dumps({str(k): v for k, v in cache.items()}, indent=2)
    )


def build_cache(
    parks: list[Park],
    *,
    refresh: bool = False,
    progress=None,
) -> dict[int, dict]:
    """Geocode and route each park, persisting incrementally so a crash mid-run
    doesn't lose work."""
    cache = {} if refresh else _load_raw()
    with httpx.Client(timeout=30.0) as client:
        for i, p in enumerate(parks, 1):
            if p.park_id in cache and cache[p.park_id].get("hours") is not None:
                if progress:
                    progress(i, len(parks), p.name, "cached")
                continue
            try:
                latlon = geocode_park(client, p.name)
                if latlon is None:
                    if progress:
                        progress(i, len(parks), p.name, "no geocode")
                    cache[p.park_id] = {"lat": None, "lon": None, "hours": None}
                    save_cache(cache)
                    time.sleep(POLITE_DELAY)
                    continue
                hours = route_hours(client, HOME_LATLON, latlon)
                cache[p.park_id] = {
                    "lat": latlon[0],
                    "lon": latlon[1],
                    "hours": hours,
                }
                if progress:
                    progress(i, len(parks), p.name, f"{hours:.1f}h" if hours else "no route")
            except httpx.HTTPError as e:
                if progress:
                    progress(i, len(parks), p.name, f"err: {e}")
                cache[p.park_id] = {"lat": None, "lon": None, "hours": None}
            save_cache(cache)
            time.sleep(POLITE_DELAY)
    return cache
