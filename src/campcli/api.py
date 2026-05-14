"""BC Parks GoingToCamp API adapter — sole Infrastructure implementation of BCParksApi."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import httpx

from .constants import (
    BASE_URL,
    CAMP_CATEGORY_IDS,
    CATALOG_PATH,
    HTTP_TIMEOUT,
    NON_GROUP_EQUIPMENT,
    USER_AGENT,
)
from .models import Map, Park
from .ports import ApiError, RateLimited


def _localized_name(loc: dict) -> str:
    values = loc.get("localizedValues") or [{}]
    v = values[0]
    return v.get("fullName") or v.get("name") or v.get("title") or "?"


def _is_campground(loc: dict) -> bool:
    cats = loc.get("resourceCategoryIds") or []
    return any(c in cats for c in CAMP_CATEGORY_IDS)


class BCParksClient:
    def __init__(
        self,
        client: httpx.Client | None = None,
        cache_path: Path = CATALOG_PATH,
    ) -> None:
        self._client = client or httpx.Client(
            base_url=BASE_URL,
            headers={"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"},
            timeout=HTTP_TIMEOUT,
        )
        self._cache_path = cache_path

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "BCParksClient":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        try:
            r = self._client.get(path, params=params)
        except httpx.HTTPError as e:
            raise ApiError(f"network error calling {path}: {e}") from e
        if r.status_code in (403, 429):
            raise RateLimited(f"{r.status_code} from {path}")
        if r.status_code >= 400:
            raise ApiError(f"{r.status_code} from {path}: {r.text[:200]}")
        return r.json()

    # ---- BCParksApi Protocol methods ----------------------------------------

    def list_parks(self, *, refresh: bool = False) -> list[Park]:
        if not refresh:
            cached = self._load_cached_parks()
            if cached is not None:
                return cached
        parks = self._fetch_parks()
        self._save_cached_parks(parks)
        return parks

    def list_maps(self, park_id: int) -> list[Map]:
        raw = self._get("/api/maps", params={"resourceLocationId": park_id})
        maps = [
            Map(map_id=m["mapId"], park_id=park_id, name=_localized_name(m))
            for m in raw
            if m.get("mapId") is not None
        ]
        maps.sort(key=lambda m: m.name)
        return maps

    def map_availability(
        self,
        *,
        park_id: int,
        map_id: int,
        start: date,
        end: date,
        party_size: int = 1,
    ) -> dict[int, list[dict[str, Any]]]:
        params = {
            "mapId": map_id,
            "resourceLocationId": park_id,
            "bookingCategoryId": 0,
            "startDate": start.isoformat(),
            "endDate": end.isoformat(),
            "isReserving": "true",
            "getDailyAvailability": "false",
            "partySize": party_size,
            "numEquipment": 1,
            "equipmentCategoryId": NON_GROUP_EQUIPMENT,
            "filterData": "[]",
        }
        resp = self._get("/api/availability/map", params=params)
        resources = resp.get("resourceAvailabilities") or {}
        return {int(k): v for k, v in resources.items()}

    def resource_details(self, *, park_id: int, map_id: int) -> Any:
        return self._get(
            "/api/resource/details",
            params={"resourceLocationId": park_id, "mapId": map_id},
        )

    # ---- Extra methods (not on Protocol) ------------------------------------

    def list_resource_locations(self) -> list[dict[str, Any]]:
        """Raw reachability check for campcli doctor. Not on Protocol."""
        return self._get("/api/resourceLocation")

    # ---- Internal helpers ---------------------------------------------------

    def _fetch_parks(self) -> list[Park]:
        locations = self._get("/api/resourceLocation")
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

    def _load_cached_parks(self) -> list[Park] | None:
        if not self._cache_path.exists():
            return None
        data = json.loads(self._cache_path.read_text())
        return [Park(**p) for p in data]

    def _save_cached_parks(self, parks: list[Park]) -> None:
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        self._cache_path.write_text(
            json.dumps([p.model_dump() for p in parks], indent=2)
        )
