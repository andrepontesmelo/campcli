"""SearchNotifier: renders cleared WeekendMatches and sends them via Telegram.

The notify/suppress decision lives in NotificationPolicy; this is the thin
sender adapter that turns a cleared Notification into a Telegram message.
"""
from __future__ import annotations

from collections.abc import Callable
from datetime import date

from .daemon_log import WARNING

from ..domain.models import WeekendMatch
from ..domain.ports import NotInterestedRepo, Telegram
from ..presentation.format import render_match_message
from .drive_times import DriveTimes
from .notification_policy import NotificationPolicy


class SearchNotifier:
    def __init__(
        self,
        telegram: Telegram,
        drive_times: DriveTimes,
        log: Callable[..., None],
        not_interested_repo: NotInterestedRepo,
        rest_days: int = 14,
    ) -> None:
        self._telegram = telegram
        self._drive_times = drive_times
        self._log = log
        self._not_interested_repo = not_interested_repo
        self._policy = NotificationPolicy(rest_days=rest_days)
        self._skip_set: set[tuple[int, date, date]] | None = None
        self._profile_id: int | None = None

    def set_log(self, log: Callable[..., None]) -> None:
        self._log = log

    def start_poll(
        self,
        booking_starts: list[date],
        blocked_park_ids: set[int],
        profile_id: int,
    ) -> None:
        self._policy.update_context(booking_starts, blocked_park_ids)
        self._profile_id = profile_id
        self._skip_set = self._not_interested_repo.load_skip_set(profile_id)

    def notify(self, match: WeekendMatch, *, chat_ids: list[str]) -> None:
        skip_key = (match.park_id, match.start_date, match.end_date)
        if self._skip_set is not None and skip_key in self._skip_set:
            return
        decision = self._policy.decide(match)
        if decision is None:
            return
        text = render_match_message(
            decision.match,
            prev_gap_days=decision.prev_gap_days,
            next_gap_days=decision.next_gap_days,
            drive_times=self._drive_times,
        )
        sent_ok = False
        for chat_id in chat_ids:
            try:
                message_id = self._telegram.send_to(chat_id, text)
                sent_ok = True
                self._not_interested_repo.record_sent(
                    message_id=message_id,
                    profile_id=self._profile_id,
                    park_id=match.park_id,
                    date_start=match.start_date,
                    date_end=match.end_date,
                )
            except Exception as e:
                self._log(f"telegram send to {chat_id} failed: {e}", WARNING)
        if sent_ok:
            self._policy.mark_sent(decision)
            self._log(
                f"notified: {match.park_name} {match.map_name} {match.start_date}"
            )
