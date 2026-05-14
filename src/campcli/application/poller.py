"""Poller — Application service for daemon poll-and-notify loop."""
from __future__ import annotations

import sys
from datetime import date

from . import command_router, filters
from ..constants import DEFAULT_PROFILE
from .drive_times import DriveTimes
from ..presentation.format import render_match_message
from ..domain.models import Booking, WeekendMatch
from ..domain.ports import BCParksApi, BlockedParkRepo, BookingRepo, Clock, SettingsRepo, Telegram
from .search import run as run_search


class Poller:
    def __init__(
        self,
        *,
        api: BCParksApi,
        telegram: Telegram,
        booking_repo: BookingRepo,
        blocked_repo: BlockedParkRepo,
        settings_repo: SettingsRepo,
        clock: Clock,
        drive_times: DriveTimes,
        profile: dict | None = None,
    ) -> None:
        self._api = api
        self._telegram = telegram
        self._booking_repo = booking_repo
        self._blocked_repo = blocked_repo
        self._settings_repo = settings_repo
        self._clock = clock
        self._drive_times = drive_times
        self._profile = profile or DEFAULT_PROFILE
        self._seen: set[tuple[int, int, date, int]] = set()
        self._verbose = (settings_repo.get_setting("verbose") or "") == "on"
        self._update_offset: int | None = None

    def start(self) -> None:
        try:
            self._telegram.send("campcli daemon started v3")
        except Exception as e:
            self.log(f"startup telegram failed: {e}")
        if self._verbose:
            self.log("verbose logging is ON")

    def tick(self) -> None:
        self._handle_commands()
        bookings = self._booking_repo.list_bookings()
        blocked_ids = {b.park_id for b in self._blocked_repo.list_blocked()}
        self.log(
            f"poll start (bookings={len(bookings)}, blocked={len(blocked_ids)}, "
            f"seen={len(self._seen)})"
        )

        def on_match(m: WeekendMatch) -> None:
            self._dispatch_match(m, bookings, blocked_ids)

        run_search(
            self._api,
            self._profile,
            drive_times=self._drive_times,
            progress=self.log,
            on_match=on_match,
        )

    def set_verbose(self, on: bool) -> None:
        self._verbose = on
        self._settings_repo.set_setting("verbose", "on" if on else "off")

    def log(self, msg: str) -> None:
        line = f"[{self._clock.now().isoformat(timespec='seconds')}] {msg}"
        print(line, file=sys.stderr, flush=True)
        if self._verbose:
            try:
                self._telegram.send(line)
            except Exception:
                pass

    def _handle_commands(self) -> None:
        updates = self._telegram.poll_updates(offset=self._update_offset)
        for upd in updates:
            self._update_offset = upd.update_id + 1
            self.log(f"received command: {upd.text!r}")
            reply = command_router.dispatch(upd.text, self)
            if reply:
                self._telegram.send(reply)

    def _dispatch_match(
        self,
        m: WeekendMatch,
        bookings: list[Booking],
        blocked_ids: set[int],
    ) -> None:
        key = (m.park_id, m.map_id, m.start_date, m.nights)
        if key in self._seen:
            return
        if not filters.should_notify(m, bookings=bookings, blocked_park_ids=blocked_ids):
            self._seen.add(key)
            return
        prev_gap, next_gap = filters.gap_days_to_nearest(m.start_date, bookings)
        text = render_match_message(
            m,
            prev_gap_days=prev_gap,
            next_gap_days=next_gap,
            drive_times=self._drive_times,
        )
        try:
            self._telegram.send(text)
            self.log(f"notified: {m.park_name} {m.map_name} {m.start_date}")
        except Exception as e:
            self.log(f"telegram send failed: {e}")
            return
        self._seen.add(key)
