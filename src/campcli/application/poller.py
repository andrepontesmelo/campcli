"""Poller — Application service for daemon poll-and-notify loop.

Multi-profile: loads all enabled profiles from ``ProfileRepo``, deduplicates
park/map API calls across profiles, and notifies per-profile.
"""
from __future__ import annotations

from collections.abc import Callable
from datetime import date, timedelta

from . import command_router, telegram_settings
from .catalog import is_bookable_map, resolve_map, resolve_park
from .daemon_log import DaemonLog, INFO, WARNING
from .command_responses import handle_one_command_batch  # noqa: F401
from ..domain.models import DriveTimes
from .telegram_users import build_verbose_chat_set
from ..domain.booking_window import max_bookable_start
from ..domain.models import Park, Profile, WeekendMatch
from ..domain.ports import BCParksApi, Clock, NotInterestedRepo, ProfileRepo, SettingsRepo, Telegram
from .search import expand_windows, is_covered
from .search_notifier import SearchNotifier
from .pricing import fee_per_night
from .availability import check_map_from_data


class Poller:
    def __init__(
        self,
        *,
        api: BCParksApi,
        telegram: Telegram,
        notifier_factory: Callable[[Profile], SearchNotifier],
        settings_repo: SettingsRepo,
        clock: Clock,
        drive_times: DriveTimes,
        profile_repo: ProfileRepo,
        not_interested_repo: NotInterestedRepo | None = None,
    ) -> None:
        self._api = api
        self._telegram = telegram
        self._notifier_factory = notifier_factory
        self._settings_repo = settings_repo
        self._clock = clock
        self._drive_times = drive_times
        self._profile_repo = profile_repo
        self._not_interested_repo = not_interested_repo

        # Cache of per-profile notifiers — persists across poll cycles so
        # NotificationPolicy dedup state (seen set) carries over.
        self._notifiers: dict[int, SearchNotifier] = {}

        # Union of all enabled profiles' tg_allowed_ids (for command auth).
        self._tg_allowed_ids: list[int] = []
        self._refresh_tg_allowed_ids()

        verbose_chats = build_verbose_chat_set(
            self._settings_repo, self._tg_allowed_ids
        )
        self._log = DaemonLog(clock, telegram, verbose_chats=verbose_chats)
        self._poll_telegram: Telegram | None = None

    def _refresh_tg_allowed_ids(self) -> None:
        """Recompute the union of ``tg_allowed_ids`` across enabled profiles."""
        self._tg_allowed_ids = telegram_settings.refresh_tg_allowed_ids(
            self._profile_repo
        )

    def set_poll_telegram(self, poll_telegram: Telegram) -> None:
        self._poll_telegram = poll_telegram

    def start(self) -> None:
        # Register bot commands
        try:
            self._telegram.set_my_commands(command_router.BOT_COMMANDS)
        except Exception as e:
            self.log(f"setMyCommands failed: {e}", WARNING)
        # Notify all authorized users who have a known chat
        for tg_id in self._tg_allowed_ids:
            chat = telegram_settings.get_chat_id(self._settings_repo, tg_id)
            if chat:
                try:
                    self._telegram.send_to(
                        chat, "campcli daemon started v3"
                    )
                except Exception as e:
                    self.log(f"startup telegram to {tg_id} failed: {e}", WARNING)

    def run_search_once(self) -> None:
        self._refresh_tg_allowed_ids()
        self.log("poll start")

        profiles = self._profile_repo.list_enabled()
        if not profiles:
            self.log("no enabled profiles — skipping poll")
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
                    park: Park = resolve_park(self._api, pq.park_query)
                except ValueError as e:
                    self.log(
                        f"profile {profile.name!r}: park query {pq.park_query!r}: {e}"
                    )
                    continue

                if pq.map_query is not None:
                    # Specific map filter.
                    try:
                        m = resolve_map(self._api, park.park_id, pq.map_query)
                    except ValueError as e:
                        self.log(
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
                        maps = self._api.list_maps(park.park_id)
                    except Exception as e:
                        self.log(
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
            self.log("no valid park pairs to check")
            return

        # ------------------------------------------------------------------
        # 2. Pre-fetch all Park / Map objects for the pairs we need to check.
        # ------------------------------------------------------------------
        all_parks = self._api.list_parks()
        park_cache: dict[int, Park] = {p.park_id: p for p in all_parks}
        for (park_id, map_id) in pair_to_profiles:
            if (park_id, map_id) not in map_cache:
                maps = self._api.list_maps(park_id)
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

            self.log(f"checking {park.name} / {map_obj.name}")

            # Determine the full date range to cover all profiles' horizons.
            today = date.today()
            max_bookable = max_bookable_start(today)
            max_horizon = max(
                (p.max_horizon_months for p in watching_profiles), default=3
            )
            range_end = today + timedelta(days=max_horizon * 30)

            # Call map_availability ONCE for the full range.
            try:
                resources = self._api.map_availability(
                    park_id=park_id,
                    map_id=map_id,
                    start=today,
                    end=range_end,
                    party_size=1,
                )
            except Exception as e:
                self.log(
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
                        park, map_obj, start, nights, resources
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
                notifier = self._notifiers.get(profile.id)
                if notifier is None:
                    notifier = self._notifier_factory(profile)
                    notifier.set_log(self.log)
                    self._notifiers[profile.id] = notifier

                notifier.start_poll([], set(), profile_id=profile.id)

                # Build chat_ids for this profile's tg_allowed_ids.
                chat_ids = [
                    cid
                    for cid in (
                        telegram_settings.get_chat_id(self._settings_repo, tid)
                        for tid in profile.tg_allowed_ids
                    )
                    if cid is not None
                ]
                for match in profile_matches:
                    notifier.notify(match, chat_ids=chat_ids)

        self.log("poll complete")

    def _get_verbose(self, tg_id: int) -> bool:
        return telegram_settings.get_verbose(self._settings_repo, tg_id)

    def set_verbose(self, tg_id: int, on: bool, chat_id: str | None = None) -> None:
        telegram_settings.set_verbose(self._settings_repo, tg_id, on)
        if chat_id:
            self._log.set_verbose(chat_id, on)
        self._refresh_verbose_chats()

    def _refresh_verbose_chats(self) -> None:
        chats = build_verbose_chat_set(
            self._settings_repo, self._tg_allowed_ids
        )
        self._log.set_verbose_chats(chats)

    def _get_chat_id_for_user(self, tg_id: int) -> str | None:
        return telegram_settings.get_chat_id(self._settings_repo, tg_id)

    def log(self, msg: str, level: int = INFO) -> None:
        self._log.log(msg, level)


