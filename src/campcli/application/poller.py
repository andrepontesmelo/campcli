"""Poller — Application service for daemon poll-and-notify loop."""
from __future__ import annotations

import sys

from . import command_router
from ..constants import DEFAULT_PROFILE
from .drive_times import DriveTimes
from ..domain.models import WeekendMatch
from ..domain.ports import BCParksApi, BlockedParkRepo, BookingRepo, Clock, SettingsRepo, Telegram
from .search import run as run_search
from .search_notifier import SearchNotifier


class Poller:
    def __init__(
        self,
        *,
        api: BCParksApi,
        telegram: Telegram,
        notifier: SearchNotifier,
        booking_repo: BookingRepo,
        blocked_repo: BlockedParkRepo,
        settings_repo: SettingsRepo,
        clock: Clock,
        drive_times: DriveTimes,
        profile: dict | None = None,
    ) -> None:
        self._api = api
        self._telegram = telegram
        self._notifier = notifier
        self._booking_repo = booking_repo
        self._blocked_repo = blocked_repo
        self._settings_repo = settings_repo
        self._clock = clock
        self._drive_times = drive_times
        self._profile = profile or DEFAULT_PROFILE
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
        self._notifier.start_poll(bookings, blocked_ids)
        self.log(
            f"poll start (bookings={len(bookings)}, blocked={len(blocked_ids)})"
        )

        def on_match(m: WeekendMatch) -> None:
            self._notifier.notify(m)

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


