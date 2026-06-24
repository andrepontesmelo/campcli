"""NotificationPolicy: the single decision of whether a WeekendMatch notifies.

Owns every suppression rule in one place — booking-adjacency (rest_days) and
dedup — plus the booking-gap computation the message needs.
Pure decision + in-memory dedup state; no I/O, no rendering.

Sender flow:
    n = policy.decide(match)        # None -> suppressed (already recorded)
    if n: render(n) ; send ; policy.mark_sent(n)

``decide`` records suppressed matches as seen immediately, but a match cleared
to send is only recorded once the caller confirms delivery via ``mark_sent``,
so a failed send is retried on the next poll.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from ..domain.models import WeekendMatch
from .filters import gap_days_to_nearest, is_too_close

_Key = tuple[int, int, date, int]


@dataclass(frozen=True)
class Notification:
    """A WeekendMatch cleared to notify, with the gaps the message renders."""

    match: WeekendMatch
    prev_gap_days: int | None
    next_gap_days: int | None


class NotificationPolicy:
    def __init__(self, rest_days: int = 14) -> None:
        self._seen: set[_Key] = set()
        self._booking_starts: list[date] = []
        self._blocked_park_ids: set[int] = set()
        self._rest_days = rest_days

    def update_context(
        self, booking_starts: list[date], blocked_park_ids: set[int]
    ) -> None:
        """Refresh the booking starts / blocked park IDs the next decisions are made against."""
        self._booking_starts = booking_starts
        self._blocked_park_ids = blocked_park_ids

    @staticmethod
    def _key(match: WeekendMatch) -> _Key:
        return (match.park_id, match.map_id, match.start_date, match.nights)

    def decide(self, match: WeekendMatch) -> Notification | None:
        """Return a Notification to send, or None if suppressed.

        Suppressed and already-seen matches return None. Suppressed matches are
        recorded as seen here; a cleared match is recorded by ``mark_sent``.
        """
        key = self._key(match)
        if key in self._seen:
            return None
        if match.park_id in self._blocked_park_ids or is_too_close(
            match.start_date, self._booking_starts, rest_days=self._rest_days,
        ):
            self._seen.add(key)
            return None
        prev_gap, next_gap = gap_days_to_nearest(match.start_date, self._booking_starts)
        return Notification(match, prev_gap, next_gap)

    def mark_sent(self, notification: Notification) -> None:
        """Record a notification as delivered so it is not sent again."""
        self._seen.add(self._key(notification.match))
