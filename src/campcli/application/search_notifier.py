from __future__ import annotations

from collections.abc import Callable
from datetime import date

from ..domain.models import Booking, WeekendMatch
from ..domain.ports import Telegram
from ..presentation.format import render_match_message
from .drive_times import DriveTimes
from .filters import gap_days_to_nearest, should_notify


class SearchNotifier:
    def __init__(
        self,
        telegram: Telegram,
        drive_times: DriveTimes,
        log: Callable[[str], None],
    ) -> None:
        self._telegram = telegram
        self._drive_times = drive_times
        self._log = log
        self._seen: set[tuple[int, int, date, int]] = set()

    def start_poll(
        self,
        bookings: list[Booking],
        blocked_park_ids: set[int],
    ) -> None:
        self._bookings = bookings
        self._blocked_park_ids = blocked_park_ids

    def notify(self, match: WeekendMatch) -> None:
        key = (match.park_id, match.map_id, match.start_date, match.nights)
        if key in self._seen:
            return
        if not should_notify(match, bookings=self._bookings, blocked_park_ids=self._blocked_park_ids):
            self._seen.add(key)
            return
        prev_gap, next_gap = gap_days_to_nearest(match.start_date, self._bookings)
        text = render_match_message(
            match,
            prev_gap_days=prev_gap,
            next_gap_days=next_gap,
            drive_times=self._drive_times,
        )
        try:
            self._telegram.send(text)
            self._log(f"notified: {match.park_name} {match.map_name} {match.start_date}")
        except Exception as e:
            self._log(f"telegram send failed: {e}")
            return
        self._seen.add(key)
