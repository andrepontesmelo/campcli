"""Search orchestration for the `campcli search` command.

Expands a profile (e.g. weekends) into concrete (start_date, nights) windows
across a horizon, fans out availability checks across drive-time-filtered
parks, and aggregates results into per-(park, map, weekend) matches.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Callable

from . import catalog
from .availability import check_map
from ..constants import DEFAULT_PROFILE, PERSONAL_MIN_START_DATE, max_bookable_start
from .drive_times import DriveTimes
from ..domain.models import Park, WeekendMatch
from ..domain.ports import BCParksApi
from .pricing import fee_per_night


def expand_windows(
    today: date, profile: dict, max_start: date | None = None,
    min_start: date | None = None,
) -> list[tuple[date, int]]:
    """Yield every (start_date, nights) in `profile.patterns` within horizon.

    Skips windows that start in the past. Horizon is approximated as
    `horizon_months * 30` days — good enough for trip discovery.
    When `max_start` is set, windows starting after it are excluded
    (BC Parks booking window constraint — only start date matters).
    When `min_start` is set, windows starting before it are excluded
    (personal minimum date filter).
    """
    horizon_days = int(profile["horizon_months"]) * 30
    end = today + timedelta(days=horizon_days)
    out: list[tuple[date, int]] = []
    d = today
    while d <= end:
        if min_start is not None and d < min_start:
            d += timedelta(days=1)
            continue
        if max_start is not None and d > max_start:
            d += timedelta(days=1)
            continue
        for weekday, nights in profile["patterns"]:
            if d.weekday() == weekday and d >= today:
                out.append((d, nights))
        d += timedelta(days=1)
    return out


def run(
    api: BCParksApi,
    profile: dict,
    *,
    drive_times: DriveTimes,
    today: date | None = None,
    limit_parks: int | None = None,
    progress: Callable[[str], None] | None = None,
    on_match: Callable[[WeekendMatch], None] | None = None,
) -> list[WeekendMatch]:
    today = today or date.today()
    windows = expand_windows(
        today, profile,
        max_start=max_bookable_start(today),
        min_start=PERSONAL_MIN_START_DATE,
    )
    parks = catalog.list_parks_filtered(
        api, drive_times=drive_times, max_hours=profile["max_drive_hours"]
    )
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
                fee = fee_per_night(start)
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


def build_profile(
    *, months: int | None = None, max_hours: float | None = None,
) -> dict:
    profile = dict(DEFAULT_PROFILE)
    if months is not None:
        profile["horizon_months"] = months
    if max_hours is not None:
        profile["max_drive_hours"] = max_hours
    return profile
