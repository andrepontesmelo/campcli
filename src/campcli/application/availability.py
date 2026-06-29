"""Availability queries: fan out across all maps of a park, return AvailableSite list."""
from __future__ import annotations

from datetime import date, timedelta

from ..domain.goingtocamp_codes import AVAILABILITY_AVAILABLE
from ..domain.models import AvailableSite, Map, Park
from ..domain.ports import BCParksApi


def _site_name(slot: dict) -> str | None:
    if "resourceName" in slot:
        return slot["resourceName"]
    return None


def _is_available(slots: list[dict]) -> bool:
    return bool(slots) and all(s.get("availability") == AVAILABILITY_AVAILABLE for s in slots)


def check_map(
    api: BCParksApi,
    park: Park,
    m: Map,
    start: date,
    nights: int,
    party_size: int,
) -> list[AvailableSite]:
    end = start + timedelta(days=nights)
    resources = api.map_availability(
        park_id=park.park_id,
        map_id=m.map_id,
        start=start,
        end=end,
        party_size=party_size,
    )
    out: list[AvailableSite] = []
    for site_id, slots in resources.items():
        if not _is_available(slots):
            continue
        out.append(
            AvailableSite(
                park_id=park.park_id,
                park_name=park.name,
                map_id=m.map_id,
                map_name=m.name,
                site_id=site_id,
                site_name=_site_name(slots[0]) if slots else None,
                start_date=start,
                end_date=end,
            )
        )
    return out


def check_map_from_data(
    park: Park,
    m: Map,
    start: date,
    nights: int,
    resources: dict[int, list[dict]],
    *,
    fetch_start: date,
) -> list[AvailableSite]:
    """Check availability for a window against pre-fetched ``map_availability`` data.

    ``resources`` is the raw ``{site_id: [slot_dicts]}`` returned by
    ``BCParksApi.map_availability(..., daily=True)`` over a wider range
    beginning at ``fetch_start``. Daily slots are **positional and date-less**:
    slot index ``i`` is the night ``fetch_start + i days``. The window
    ``[start, start + nights)`` therefore maps to slot indices
    ``[offset, offset + nights)`` where ``offset = (start - fetch_start).days``.
    A site is available for the window only if every one of those nights is
    present and AVAILABLE.
    """
    end = start + timedelta(days=nights)
    offset = (start - fetch_start).days
    out: list[AvailableSite] = []
    if offset < 0:
        return out
    for site_id, slots in resources.items():
        window_slots = slots[offset : offset + nights]
        if len(window_slots) < nights or not _is_available(window_slots):
            continue
        out.append(
            AvailableSite(
                park_id=park.park_id,
                park_name=park.name,
                map_id=m.map_id,
                map_name=m.name,
                site_id=site_id,
                site_name=_site_name(window_slots[0]),
                start_date=start,
                end_date=end,
            )
        )
    return out


def check_park(
    api: BCParksApi,
    park: Park,
    start: date,
    nights: int,
    party_size: int = 1,
    map_filter: int | None = None,
) -> list[AvailableSite]:
    maps = api.list_maps(park.park_id)
    if map_filter is not None:
        maps = [m for m in maps if m.map_id == map_filter]
    results: list[AvailableSite] = []
    for m in maps:
        results.extend(check_map(api, park, m, start, nights, party_size))
    return results
