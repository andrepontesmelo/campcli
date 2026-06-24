"""Search orchestration for the `campcli search` command.

Expands profile patterns into concrete (start_date, nights) windows across
a horizon, fans out availability checks across drive-time-filtered parks,
and aggregates results into per-(park, map, weekend) matches.
"""
from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import date, timedelta

from . import catalog
from .availability import check_map
from ..domain.booking_window import max_bookable_start
from .drive_times import DriveTimes
from ..domain.models import Park, WeekendMatch
from ..domain.ports import BCParksApi
from .pricing import fee_per_night
from .profile import Profile


def expand_windows(
    today: date, profile: Profile, max_start: date | None = None,
    min_start: date | None = None,
) -> list[tuple[date, int]]:
    """Yield every (start_date, nights) in *profile.patterns* within horizon.

    Skips windows that start in the past. Horizon is approximated as
    ``max_horizon_months * 30`` days — good enough for trip discovery.
    When *max_start* is set, windows starting after it are excluded
    (BC Parks booking window constraint — only start date matters).
    When *min_start* is set, windows starting before it are excluded.
    """
    horizon_days = profile.max_horizon_months * 30
    end = today + timedelta(days=horizon_days)
    out: list[tuple[date, int]] = []
    patterns = profile.pattern_tuples()
    d = today
    while d <= end:
        if min_start is not None and d < min_start:
            d += timedelta(days=1)
            continue
        if max_start is not None and d > max_start:
            d += timedelta(days=1)
            continue
        # TODO subtask 9ggclfjc: full enumeration rewrite — expand min/max
        for weekday, span_nights, _min_nights, _max_nights in patterns:
            if d.weekday() == weekday and d >= today:
                out.append((d, span_nights))
        d += timedelta(days=1)
    return out


def run(
    api: BCParksApi,
    profile: Profile,
    *,
    drive_times: DriveTimes,
    today: date | None = None,
    limit_parks: int | None = None,
    allowed_park_ids: dict[int, set[int] | None] | None = None,
    progress: Callable[[str], None] | None = None,
) -> Iterator[WeekendMatch]:
    """Yield WeekendMatches as they are found.

    *profile* is a :class:`Profile` value object with patterns, horizon,
    drive-hour limit, and resolved allowed-park IDs.

    When *allowed_park_ids* is provided, only parks (and optionally maps)
    appearing in the allowlist are checked. ``None`` for a map set means all
    non-walk-in maps are permitted.

    *progress* is an optional side-channel for scan status ("[3/120] Park").
    Matches are streamed to the caller via the return value — the caller
    decides what to do with each (notify, collect, render).
    """
    today = today or date.today()
    min_start = profile.min_start_date_parsed()
    windows = expand_windows(
        today, profile,
        max_start=max_bookable_start(today),
        min_start=min_start,
    )
    parks = catalog.list_parks_filtered(
        api, drive_times=drive_times, max_hours=profile.max_drive_hours,
    )
    if limit_parks is not None:
        parks = parks[:limit_parks]

    # Pre-filter by allowlist so progress matches checked parks.
    if allowed_park_ids is not None:
        parks = [p for p in parks if p.park_id in allowed_park_ids]

    if not parks:
        return

    total = len(parks)
    for i, park in enumerate(parks, 1):
        if progress:
            progress(f"[{i}/{total}] {park.name}")

        if allowed_park_ids is not None:
            allowed_maps = allowed_park_ids[park.park_id]

        try:
            maps = api.list_maps(park.park_id)
        except Exception as e:
            if progress:
                progress(f"  ! maps fetch failed for {park.name}: {e}")
            continue

        for m in maps:
            if "walk-in" in m.name.lower() or "walk in" in m.name.lower():
                continue
            # Apply map-level allowlist.
            if allowed_park_ids is not None and allowed_maps is not None:
                if m.map_id not in allowed_maps:
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
                yield match
