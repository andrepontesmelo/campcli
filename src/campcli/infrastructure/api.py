"""BC Parks GoingToCamp API adapter — sole Infrastructure implementation of BCParksApi."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from time import monotonic, sleep
from typing import Any, Callable

import httpx

from ..constants import BASE_URL, CATALOG_PATH
from ..constants import DEFAULT_REQUEST_INTERVAL_SECS
from ..domain.goingtocamp_codes import CAMP_CATEGORY_IDS, NON_GROUP_EQUIPMENT
from ..domain.models import Map, Park
from ..domain.ports import ApiError, RateLimited

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)
HTTP_TIMEOUT = 30.0


def _localized_name(loc: dict) -> str:
    values = loc.get("localizedValues") or [{}]
    v = values[0]
    return v.get("fullName") or v.get("name") or v.get("title") or "?"


def _is_campground(loc: dict) -> bool:
    cats = loc.get("resourceCategoryIds") or []
    return any(c in cats for c in CAMP_CATEGORY_IDS)


def _summarize(body: str) -> str:
    """Return a one-line summary of a JSON API response body."""
    n = len(body)
    preview = body[:200].replace("\n", " ").replace("\r", "")
    try:
        data = json.loads(body)
        if isinstance(data, list):
            preview = f"list[{len(data)}]"
        elif isinstance(data, dict):
            preview = f"dict({len(data)} keys)"
    except (json.JSONDecodeError, ValueError):
        pass
    return f"{n} chars, {preview}"


class BCParksClient:
    def __init__(
        self,
        client: httpx.Client | None = None,
        cache_path: Path = CATALOG_PATH,
        min_interval_secs: float = DEFAULT_REQUEST_INTERVAL_SECS,
        sleep: Callable[[float], None] = sleep,
        on_request: Callable[[str, dict[str, Any], int, str], None] | None = None,
    ) -> None:
        self._client = client or httpx.Client(
            base_url=BASE_URL,
            headers={"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"},
            timeout=HTTP_TIMEOUT,
        )
        self._cache_path = cache_path
        self._min_interval_secs = min_interval_secs
        self._sleep = sleep
        self._on_request = on_request
        self._last_request_at: float | None = None

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "BCParksClient":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        now = monotonic()
        if self._last_request_at is not None and self._min_interval_secs > 0:
            wait = self._min_interval_secs - (now - self._last_request_at)
            if wait > 0:
                self._sleep(wait)
        self._last_request_at = monotonic()
        try:
            r = self._client.get(path, params=params)
        except httpx.HTTPError as e:
            if self._on_request:
                self._on_request(path, params or {}, 0, f"network error: {e}")
            raise ApiError(f"network error calling {path}: {e}") from e
        if r.status_code in (403, 429):
            if self._on_request:
                self._on_request(path, params or {}, r.status_code, "rate limited")
            raise RateLimited(f"{r.status_code} from {path}")
        if r.status_code >= 400:
            if self._on_request:
                self._on_request(path, params or {}, r.status_code, r.text[:200])
            raise ApiError(f"{r.status_code} from {path}: {r.text[:200]}")
        if self._on_request:
            self._on_request(path, params or {}, r.status_code, _summarize(r.text))
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

    # resource_details: Protocol requirement, no implementation needed in current codepaths

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
