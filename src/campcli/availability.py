"""Availability queries: fan out across all maps of a park, return AvailableSite list."""
from __future__ import annotations

from datetime import date, timedelta

from .api import BCParksClient
from .catalog import fetch_maps
from .constants import AVAILABILITY_AVAILABLE
from .models import AvailableSite, Map, Park


def _site_name(slot: dict) -> str | None:
    if "resourceName" in slot:
        return slot["resourceName"]
    return None


def _is_available(slots: list[dict]) -> bool:
    return bool(slots) and all(s.get("availability") == AVAILABILITY_AVAILABLE for s in slots)


def check_map(
    client: BCParksClient,
    park: Park,
    m: Map,
    start: date,
    nights: int,
    party_size: int,
) -> list[AvailableSite]:
    end = start + timedelta(days=nights)
    resp = client.map_availability(
        park_id=park.park_id,
        map_id=m.map_id,
        start=start,
        end=end,
        party_size=party_size,
    )
    resources = resp.get("resourceAvailabilities") or {}
    out: list[AvailableSite] = []
    for site_id_str, slots in resources.items():
        if not _is_available(slots):
            continue
        out.append(
            AvailableSite(
                park_id=park.park_id,
                park_name=park.name,
                map_id=m.map_id,
                map_name=m.name,
                site_id=int(site_id_str),
                site_name=_site_name(slots[0]) if slots else None,
                start_date=start,
                end_date=end,
            )
        )
    return out


def check_park(
    client: BCParksClient,
    park: Park,
    start: date,
    nights: int,
    party_size: int = 1,
    map_filter: int | None = None,
) -> list[AvailableSite]:
    maps = fetch_maps(client, park.park_id)
    if map_filter is not None:
        maps = [m for m in maps if m.map_id == map_filter]
    results: list[AvailableSite] = []
    for m in maps:
        results.extend(check_map(client, park, m, start, nights, party_size))
    return results
