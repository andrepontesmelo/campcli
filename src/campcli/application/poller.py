"""Poller — Application service for daemon poll-and-notify loop.

Multi-profile: loads all enabled profiles from ``ProfileRepo``, deduplicates
park/map API calls across profiles, and notifies per-profile.
"""
from __future__ import annotations

import threading
import time
from collections.abc import Callable
from datetime import date, timedelta

from . import command_router
from .catalog import resolve_map, resolve_park
from .daemon_log import DaemonLog
from .drive_times import DriveTimes
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
        self._update_offset: int | None = None

    def _refresh_tg_allowed_ids(self) -> None:
        """Recompute the union of ``tg_allowed_ids`` across enabled profiles."""
        profiles = self._profile_repo.list_enabled()
        ids: set[int] = set()
        for p in profiles:
            ids.update(p.tg_allowed_ids)
        self._tg_allowed_ids = sorted(ids)

    def set_poll_telegram(self, poll_telegram: Telegram) -> None:
        self._poll_telegram = poll_telegram

    def start(self) -> None:
        # Register bot commands
        try:
            self._telegram.set_my_commands(command_router.BOT_COMMANDS)
        except Exception as e:
            self.log(f"setMyCommands failed: {e}")
        # Notify all authorized users who have a known chat
        for tg_id in self._tg_allowed_ids:
            chat = self._settings_repo.get_setting(f"chat:{tg_id}")
            if chat:
                try:
                    self._telegram.send_to(
                        chat, "campcli daemon started v3"
                    )
                except Exception as e:
                    self.log(f"startup telegram to {tg_id} failed: {e}")

    def tick(self) -> None:
        self._handle_commands()
        self.run_search_once()

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
                        if "walk-in" in m.name.lower() or "walk in" in m.name.lower():
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
                        self._settings_repo.get_setting(f"chat:{tid}")
                        for tid in profile.tg_allowed_ids
                    )
                    if cid is not None
                ]
                for match in profile_matches:
                    notifier.notify(match, chat_ids=chat_ids)

        self.log("poll complete")

    def handle_commands_forever(
        self, stop: threading.Event, long_poll_timeout: int = 25
    ) -> None:
        poll = self._poll_telegram or self._telegram
        while not stop.is_set():
            try:
                updates = poll.poll_updates(
                    offset=self._update_offset,
                    long_poll_timeout=long_poll_timeout,
                )
                for upd in updates:
                    self._process_update(upd)
            except Exception as e:
                self.log(f"command loop error: {e}")
                time.sleep(1)

    def _get_verbose(self, tg_id: int) -> bool:
        val = self._settings_repo.get_setting(f"verbose:{tg_id}")
        return val == "on"

    def set_verbose(self, tg_id: int, on: bool, chat_id: str | None = None) -> None:
        self._settings_repo.set_setting(
            f"verbose:{tg_id}", "on" if on else "off"
        )
        if chat_id:
            self._log.set_verbose(chat_id, on)
        self._refresh_verbose_chats()

    def _refresh_verbose_chats(self) -> None:
        chats = build_verbose_chat_set(
            self._settings_repo, self._tg_allowed_ids
        )
        self._log.set_verbose_chats(chats)

    def _get_chat_id_for_user(self, tg_id: int) -> str | None:
        return self._settings_repo.get_setting(f"chat:{tg_id}")

    def log(self, msg: str) -> None:
        self._log.log(msg)

    def _handle_commands(self) -> None:
        updates = self._telegram.poll_updates(offset=self._update_offset)
        for upd in updates:
            self._process_update(upd)

    def _process_update(self, upd) -> None:
        self._update_offset = upd.update_id + 1
        self.log(f"received update: {upd.text or '(callback)'!r}")
        # Last-seen chat tracking (authorized users only)
        if (
            upd.from_id is not None
            and upd.chat_id
            and upd.from_id in self._tg_allowed_ids
        ):
            old = self._settings_repo.get_setting(
                f"chat:{upd.from_id}"
            )
            if old != upd.chat_id:
                self._settings_repo.set_setting(
                    f"chat:{upd.from_id}", upd.chat_id
                )
                self._refresh_verbose_chats()
        result = command_router.dispatch(
            upd, self, self._tg_allowed_ids
        )
        if result is None:
            # Still answer the callback query if applicable
            if upd.callback_query_id:
                try:
                    self._telegram.answer_callback_query(
                        upd.callback_query_id
                    )
                except Exception:
                    pass
            return
        # Always answer callback queries to dismiss the Telegram spinner,
        # even for unauthorized users (dispatch may return "reply" type).
        if upd.callback_query_id and result.get("type") != "callback":
            try:
                self._telegram.answer_callback_query(
                    upd.callback_query_id
                )
            except Exception:
                pass
        t = result.get("type")
        if t == "reply":
            text = result["text"]
            self._telegram.send_to(upd.chat_id, text)
            self.log(f"replied: {text}")
        elif t == "inline_keyboard":
            text = result["text"]
            buttons = result["buttons"]
            self._telegram.send_inline_keyboard(
                upd.chat_id, text, buttons
            )
            self.log(f"sent inline keyboard: {text}")
        elif t == "callback":
            cb_id = result.get("callback_query_id", "")
            text = result.get("text", "")
            # Answer callback query to dismiss spinner
            try:
                self._telegram.answer_callback_query(cb_id)
            except Exception:
                pass
            # Edit the original message to reflect new state
            msg_id = upd.message_id
            if msg_id:
                try:
                    self._telegram.edit_message_reply_markup(
                        upd.chat_id, msg_id, text=text
                    )
                except Exception:
                    pass
            self.log(f"callback answered: {text}")
