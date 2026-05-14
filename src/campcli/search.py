"""Search orchestration for the `campcli search` command.

Expands a profile (e.g. weekends) into concrete (start_date, nights) windows
across a horizon, fans out availability checks across drive-time-filtered
parks, and aggregates results into per-(park, map, weekend) matches.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Callable

from .availability import check_map
from .drive_times import load_cache as load_drive_cache
from .models import Park, WeekendMatch
from .ports import BCParksApi
from .pricing import fee_per_night


def expand_windows(today: date, profile: dict) -> list[tuple[date, int]]:
    """Yield every (start_date, nights) in `profile.patterns` within horizon.

    Skips windows that start in the past. Horizon is approximated as
    `horizon_months * 30` days — good enough for trip discovery.
    """
    horizon_days = int(profile["horizon_months"]) * 30
    end = today + timedelta(days=horizon_days)
    out: list[tuple[date, int]] = []
    d = today
    while d <= end:
        for weekday, nights in profile["patterns"]:
            if d.weekday() == weekday and d >= today:
                out.append((d, nights))
        d += timedelta(days=1)
    return out


def filter_parks_by_drive(parks: list[Park], max_hours: float) -> list[Park]:
    cache = load_drive_cache()
    if not cache:
        return []
    return [
        p for p in parks
        if (h := cache.get(p.park_id, {}).get("hours")) is not None and h <= max_hours
    ]


def run(
    api: BCParksApi,
    profile: dict,
    *,
    today: date | None = None,
    limit_parks: int | None = None,
    progress: Callable[[str], None] | None = None,
    on_match: Callable[[WeekendMatch], None] | None = None,
) -> list[WeekendMatch]:
    today = today or date.today()
    windows = expand_windows(today, profile)
    parks = api.list_parks()
    parks = filter_parks_by_drive(parks, profile["max_drive_hours"])
    if limit_parks is not None:
        parks = parks[:limit_parks]

    if not parks:
        return []

    matches: list[WeekendMatch] = []
    total = len(parks)
    for i, park in enumerate(parks, 1):
        if progress:
            progress(f"[{i}/{total}] {park.name}")
        try:
            maps = api.list_maps(park.park_id)
        except Exception as e:
            if progress:
                progress(f"  ! maps fetch failed for {park.name}: {e}")
            continue

        for m in maps:
            if "walk-in" in m.name.lower() or "walk in" in m.name.lower():
                continue
            two_night_starts: set[date] = set()
            map_windows = sorted(windows, key=lambda w: (w[0], -w[1]))
            for start, nights in map_windows:
                if nights == 1 and (
                    start in two_night_starts
                    or (start - timedelta(days=1)) in two_night_starts
                ):
                    continue
                try:
                    sites = check_map(api, park, m, start, nights, party_size=1)
                except Exception:
                    continue
                if not sites:
                    continue
                if nights == 2:
                    two_night_starts.add(start)
                fee = fee_per_night(api, park.park_id, m.map_id, start)
                match = WeekendMatch(
                    park_id=park.park_id,
                    park_name=park.name,
                    map_id=m.map_id,
                    map_name=m.name,
                    start_date=start,
                    end_date=start + timedelta(days=nights),
                    nights=nights,
                    available_count=len(sites),
                    fee_per_night=fee,
                )
                matches.append(match)
                if on_match:
                    try:
                        on_match(match)
                    except Exception as e:
                        if progress:
                            progress(f"  ! on_match callback failed: {e}")
    return matches
