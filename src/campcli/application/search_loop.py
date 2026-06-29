"""Search loop — module-level ``run_search_once`` extracted from Poller.

Module-level function so it is testable without constructing a full Poller
(which needs api, telegram, notifier_factory, profile_repo, etc.).

Multi-profile: loads all enabled profiles from ``ProfileRepo``, deduplicates
park/map API calls across profiles, and notifies per-profile.
"""
from __future__ import annotations

from collections.abc import Callable
from datetime import date, timedelta

from ..domain.booking_window import max_bookable_start
from ..domain.models import DriveTimes, Park, Profile, WeekendMatch
from ..domain.ports import BCParksApi, Clock, NotInterestedRepo, ProfileRepo, SettingsRepo
from . import telegram_settings
from .availability import check_map_from_data
from .catalog import is_bookable_map, resolve_map, resolve_park
from .daemon_log import INFO, WARNING
from .pricing import fee_per_night
from .search import expand_windows, is_covered
from .search_notifier import SearchNotifier


def run_search_once(
    *,
    api: BCParksApi,
    profile_repo: ProfileRepo,
    settings_repo: SettingsRepo,
    drive_times: DriveTimes,
    not_interested_repo: NotInterestedRepo | None = None,
    clock: Clock,
    notifier_factory: Callable[..., SearchNotifier],
    notifiers: dict[int, SearchNotifier],
    log: Callable[..., None],
) -> None:
    """Run one poll cycle: check availability for all enabled profiles.

    Args:
        api: BC Parks API client.
        profile_repo: Source of enabled profiles.
        settings_repo: For per-user settings (chat ids).
        drive_times: Drive-time value object (passed to notifier factory).
        not_interested_repo: For suppressing previously declined matches.
        clock: System clock.
        notifier_factory: Callable that creates a :class:`SearchNotifier`
            for a given :class:`Profile`.
        notifiers: Mutable cache mapping profile id → notifier instance.
            The cache persists across calls so that ``NotificationPolicy``
            dedup state (the seen set) carries over.
        log: Logging callable (msg, level=INFO).
    """
    _ = clock  # kept in signature for future port consistency

    log("poll start")

    profiles = profile_repo.list_enabled()
    if not profiles:
        log("no enabled profiles — skipping poll")
        return

    # ------------------------------------------------------------------
    # 1. Resolve each profile's ParkQuery into concrete (park, map) pairs
    #    and build a map: (park_id, map_id) → [Profile, …].
    # ------------------------------------------------------------------
    pair_to_profiles: dict[tuple[int, int], list[Profile]] = {}
    seen_pair: set[tuple[int, int, int]] = set()  # (park_id, map_id, profile_id)
    map_cache: dict[tuple[int, int], object] = {}

    for profile in profiles:
        for pq in profile.parks:
            try:
                park: Park = resolve_park(api, pq.park_query)
            except ValueError as e:
                log(
                    f"profile {profile.name!r}: park query {pq.park_query!r}: {e}"
                )
                continue

            if pq.map_query is not None:
                # Specific map filter.
                try:
                    m = resolve_map(api, park.park_id, pq.map_query)
                except ValueError as e:
                    log(
                        f"profile {profile.name!r}: map {pq.map_query!r}: {e}"
                    )
                    continue
                key = (park.park_id, m.map_id)
                sp = (park.park_id, m.map_id, profile.id)
                if sp not in seen_pair:
                    seen_pair.add(sp)
                    pair_to_profiles.setdefault(key, []).append(profile)
            else:
                # All non-walk-in maps for this park.
                try:
                    maps = api.list_maps(park.park_id)
                except Exception as e:
                    log(
                        f"profile {profile.name!r}: maps fetch failed: {e}"
                    )
                    continue
                for m in maps:
                    if not is_bookable_map(m):
                        continue
                    map_cache[(park.park_id, m.map_id)] = m
                    key = (park.park_id, m.map_id)
                    sp = (park.park_id, m.map_id, profile.id)
                    if sp not in seen_pair:
                        seen_pair.add(sp)
                        pair_to_profiles.setdefault(key, []).append(profile)

    if not pair_to_profiles:
        log("no valid park pairs to check")
        return

    # ------------------------------------------------------------------
    # 2. Pre-fetch all Park / Map objects for the pairs we need to check.
    # ------------------------------------------------------------------
    all_parks = api.list_parks()
    park_cache: dict[int, Park] = {p.park_id: p for p in all_parks}
    for (park_id, map_id) in pair_to_profiles:
        if (park_id, map_id) not in map_cache:
            maps = api.list_maps(park_id)
            for m in maps:
                if m.map_id == map_id:
                    map_cache[(park_id, map_id)] = m
                    break

    # ------------------------------------------------------------------
    # 3. Process each unique (park, map) pair sequentially.
    # ------------------------------------------------------------------
    for (park_id, map_id), watching_profiles in pair_to_profiles.items():
        park = park_cache.get(park_id)
        map_obj = map_cache.get((park_id, map_id))
        if park is None or map_obj is None:
            continue

        log(f"checking {park.name} / {map_obj.name}")

        # Determine the full date range to cover all profiles' horizons.
        today = date.today()
        max_bookable = max_bookable_start(today)
        max_horizon = max(
            (p.max_horizon_months for p in watching_profiles), default=3
        )
        range_end = today + timedelta(days=max_horizon * 30)

        # Call map_availability ONCE for the full range.
        try:
            resources = api.map_availability(
                park_id=park_id,
                map_id=map_id,
                start=today,
                end=range_end,
                party_size=1,
                daily=True,
            )
        except Exception as e:
            log(
                f"  availability fetch failed for {park.name}/{map_obj.name}: {e}"
            )
            continue

        # Collect per-profile windows (no additional API calls).
        profile_windows: dict[int | None, list[tuple[date, int]]] = {}
        for profile in watching_profiles:
            min_start = (
                date.fromisoformat(profile.min_start_date)
                if profile.min_start_date
                else None
            )
            windows = expand_windows(
                today,
                profile,
                max_start=max_bookable,
                min_start=min_start,
            )
            profile_windows[profile.id] = windows

        # ------------------------------------------------------------------
        # 4. Fan out results per-profile with prefer-longest dedup.
        # ------------------------------------------------------------------
        for profile in watching_profiles:
            profile_matches: list[WeekendMatch] = []
            accepted: list[tuple[date, int]] = []
            windows = sorted(
                profile_windows.get(profile.id, []),
                key=lambda w: (w[0], -w[1]),
            )
            for start, nights in windows:
                if is_covered(start, nights, accepted):
                    continue
                sites = check_map_from_data(
                    park, map_obj, start, nights, resources, fetch_start=today
                )
                if not sites:
                    continue
                accepted.append((start, nights))
                fee = fee_per_night(start)
                match = WeekendMatch(
                    park_id=park_id,
                    park_name=park.name,
                    map_id=map_id,
                    map_name=map_obj.name,
                    start_date=start,
                    end_date=start + timedelta(days=nights),
                    nights=nights,
                    available_count=len(sites),
                    fee_per_night=fee,
                )
                profile_matches.append(match)

            if not profile_matches:
                continue

            # Get or create per-profile notifier.
            notifier = notifiers.get(profile.id)
            if notifier is None:
                notifier = notifier_factory(profile)
                notifier.set_log(log)
                notifiers[profile.id] = notifier

            notifier.start_poll([], set(), profile_id=profile.id)

            # Build chat_ids for this profile's tg_allowed_ids.
            chat_ids = [
                cid
                for cid in (
                    telegram_settings.get_chat_id(settings_repo, tid)
                    for tid in profile.tg_allowed_ids
                )
                if cid is not None
            ]
            for match in profile_matches:
                notifier.notify(match, chat_ids=chat_ids)

    log("poll complete")
