"""SearchNotifier: renders cleared WeekendMatches and sends them via Telegram.

The notify/suppress decision lives in NotificationPolicy; this is the thin
sender adapter that turns a cleared Notification into a Telegram message.
"""
from __future__ import annotations

from collections.abc import Callable

from ..domain.models import Booking, WeekendMatch
from ..domain.ports import Telegram
from ..presentation.format import render_match_message
from .drive_times import DriveTimes
from .notification_policy import NotificationPolicy


class SearchNotifier:
    def __init__(
        self,
        telegram: Telegram,
        drive_times: DriveTimes,
        log: Callable[[str], None],
        rest_days: int = 14,
    ) -> None:
        self._telegram = telegram
        self._drive_times = drive_times
        self._log = log
        self._policy = NotificationPolicy(rest_days=rest_days)

    def start_poll(
        self,
        bookings: list[Booking],
        blocked_park_ids: set[int],
    ) -> None:
        self._policy.update_context(bookings, blocked_park_ids)

    def notify(self, match: WeekendMatch) -> None:
        decision = self._policy.decide(match)
        if decision is None:
            return
        text = render_match_message(
            decision.match,
            prev_gap_days=decision.prev_gap_days,
            next_gap_days=decision.next_gap_days,
            drive_times=self._drive_times,
        )
        try:
            self._telegram.send(text)
            self._log(
                f"notified: {match.park_name} {match.map_name} {match.start_date}"
            )
        except Exception as e:
            self._log(f"telegram send failed: {e}")
            return
        self._policy.mark_sent(decision)
