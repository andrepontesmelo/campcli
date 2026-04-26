"""Thin httpx wrapper for the BC Parks GoingToCamp API.

Endpoints validated in the investigation (see test-report.md, t2/t3 scripts).
This is the only module that talks HTTP — all other modules go through here.
"""
from __future__ import annotations

from datetime import date
from typing import Any

import httpx

from .constants import BASE_URL, HTTP_TIMEOUT, NON_GROUP_EQUIPMENT, USER_AGENT


class ApiError(RuntimeError):
    pass


class RateLimited(ApiError):
    pass


class BCParksClient:
    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client(
            base_url=BASE_URL,
            headers={"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"},
            timeout=HTTP_TIMEOUT,
        )

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

    def list_resource_locations(self) -> list[dict[str, Any]]:
        return self._get("/api/resourceLocation")

    def list_maps_for_park(self, park_id: int) -> list[dict[str, Any]]:
        """Maps (sub-areas) for a single park.

        The `resourceLocationId` query param is mandatory — without it the API
        returns the region tree, which was the bug that broke camply.
        """
        return self._get("/api/maps", params={"resourceLocationId": park_id})

    def resource_details(self, *, park_id: int, map_id: int) -> Any:
        """Fetch map/resource details — used to extract per-site fee structure."""
        return self._get(
            "/api/resource/details",
            params={"resourceLocationId": park_id, "mapId": map_id},
        )

    def map_availability(
        self,
        *,
        park_id: int,
        map_id: int,
        start: date,
        end: date,
        party_size: int = 1,
        equipment_category_id: int = NON_GROUP_EQUIPMENT,
    ) -> dict[str, Any]:
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
            "equipmentCategoryId": equipment_category_id,
            "filterData": "[]",
        }
        return self._get("/api/availability/map", params=params)
