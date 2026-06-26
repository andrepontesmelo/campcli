"""Search orchestration for the ``campcli search`` command.

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
from .catalog import is_bookable_map, resolve_profile_parks
from .drive_times import DriveTimes
from ..domain.models import Park, PatternSpec, Profile, WeekendMatch
from ..domain.ports import BCParksApi
from .pricing import fee_per_night

_EXPLOSION_THRESHOLD = 10


def _emit_windows_for_anchor(
    anchor: date,
    span_nights: int,
    min_nights: int,
    max_nights: int,
    today: date,
    min_start: date | None,
    max_start: date | None,
) -> list[tuple[date, int]]:
    """Emit (start, nights) windows anchored at *anchor* for a single pattern."""
    out: list[tuple[date, int]] = []
    for o in range(0, span_nights - min_nights + 1):
        for n in range(min_nights, max_nights + 1):
            if o + n > span_nights:
                continue
            start = anchor + timedelta(days=o)
            if start < today:
                continue
            if min_start is not None and start < min_start:
                continue
            if max_start is not None and start > max_start:
                continue
            out.append((start, n))
    return out


def _enumerate_pattern(
    today: date,
    end: date,
    pattern: PatternSpec,
    min_start: date | None,
    max_start: date | None,
) -> list[tuple[date, int]]:
    """Enumerate windows for a single pattern within [today, end]."""
    weekday, span_nights, min_nights, max_nights = pattern
    out: list[tuple[date, int]] = []
    d = today
    while d <= end:
        if d.weekday() != weekday:
            d += timedelta(days=1)
            continue
        out.extend(_emit_windows_for_anchor(
            anchor=d,
            span_nights=span_nights,
            min_nights=min_nights,
            max_nights=max_nights,
            today=today,
            min_start=min_start,
            max_start=max_start,
        ))
        d += timedelta(days=1)
    return out


def expand_windows(
    today: date, profile: Profile, max_start: date | None = None,
    min_start: date | None = None,
    warn: Callable[[str], None] | None = None,
) -> list[tuple[date, int]]:
    """Yield every (start_date, nights) in *profile.patterns* within horizon.

    Skips windows that start in the past. Horizon is approximated as
    ``max_horizon_months * 30`` days — good enough for trip discovery.
    When *max_start* is set, windows starting after it are excluded
    (BC Parks booking window constraint — only start date matters).
    When *min_start* is set, windows starting before it are excluded.

    *warn* is an optional side-channel for explosion warnings.
    """
    horizon_days = profile.max_horizon_months * 30
    end = today + timedelta(days=horizon_days)
    out: list[tuple[date, int]] = []
    patterns = profile.patterns  # list[PatternSpec]
    for i, pattern in enumerate(patterns):
        pattern_windows = _enumerate_pattern(
            today, end, pattern, min_start, max_start,
        )
        if len(pattern_windows) > _EXPLOSION_THRESHOLD and warn is not None:
            warn(
                f"warning: pattern #{i} {pattern!r} expanded to "
                f"{len(pattern_windows)} windows (threshold="
                f"{_EXPLOSION_THRESHOLD}); consider tightening the span"
            )
        out.extend(pattern_windows)
    return out


def is_covered(
    start: date,
    nights: int,
    accepted: list[tuple[date, int]],
) -> bool:
    """Return True if *start* / *nights* is fully within any accepted range."""
    end = start + timedelta(days=nights)
    return any(
        a_start <= start and end <= a_start + timedelta(days=a_nights)
        for (a_start, a_nights) in accepted
    )


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
    min_start = (
        date.fromisoformat(profile.min_start_date)
        if profile.min_start_date
        else None
    )
    windows = expand_windows(
        today, profile,
        max_start=max_bookable_start(today),
        min_start=min_start,
        warn=progress,
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
            if not is_bookable_map(m):
                continue
            # Apply map-level allowlist.
            if allowed_park_ids is not None and allowed_maps is not None:
                if m.map_id not in allowed_maps:
                    continue

            accepted_ranges: list[tuple[date, int]] = []
            map_windows = sorted(windows, key=lambda w: (w[0], -w[1]))
            for start, nights in map_windows:
                # Skip if a longer stay already covers this candidate's range.
                if is_covered(start, nights, accepted_ranges):
                    continue
                try:
                    sites = check_map(api, park, m, start, nights, party_size=1)
                except Exception:
                    continue
                if not sites:
                    continue
                accepted_ranges.append((start, nights))
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
