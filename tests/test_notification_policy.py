"""Pure tests for NotificationPolicy — the whole notify/suppress decision.

Before the refactor these rules were only reachable through SearchNotifier and
its Telegram + render dependencies; now the decision is a pure function of
(match, bookings, blocked) and is asserted directly.
"""
from datetime import date

from campcli.application.notification_policy import NotificationPolicy
from campcli.domain.models import Booking, WeekendMatch


def make_match(**kw):
    defaults = dict(
        park_id=1, park_name="Bowron Lake", map_id=10, map_name="Main",
        start_date=date(2026, 8, 15), end_date=date(2026, 8, 17),
        nights=2, available_count=1,
    )
    defaults.update(kw)
    return WeekendMatch(**defaults)


def make_booking(start: date) -> Booking:
    return Booking(park_id=99, park_name="Other", start_date=start,
                   end_date=start)


class TestDecide:
    def test_clear_match_returns_notification(self):
        policy = NotificationPolicy()
        n = policy.decide(make_match())
        assert n is not None
        assert n.match.park_id == 1

    def test_blocked_park_suppressed(self):
        policy = NotificationPolicy()
        policy.update_context([], {1})
        assert policy.decide(make_match()) is None

    def test_booking_within_rest_days_suppressed(self):
        policy = NotificationPolicy()
        # 13 days from the match start -> inside the 14-day REST window
        policy.update_context([make_booking(date(2026, 8, 28))], set())
        assert policy.decide(make_match()) is None

    def test_booking_outside_rest_days_clears(self):
        policy = NotificationPolicy()
        policy.update_context([make_booking(date(2026, 9, 1))], set())
        assert policy.decide(make_match()) is not None

    def test_rest_days_zero_disables_suppression(self):
        """When rest_days=0, a same-day booking does not suppress."""
        policy = NotificationPolicy(rest_days=0)
        # Same day as match start (Aug 15).
        policy.update_context([make_booking(date(2026, 8, 15))], set())
        assert policy.decide(make_match()) is not None


class TestDedup:
    def test_cleared_match_only_sent_after_mark_sent(self):
        policy = NotificationPolicy()
        m = make_match()
        n = policy.decide(m)
        # not yet recorded: a failed send should let it retry
        assert policy.decide(m) is not None
        policy.mark_sent(n)
        assert policy.decide(m) is None

    def test_suppressed_match_recorded_immediately(self):
        policy = NotificationPolicy()
        policy.update_context([], {1})
        m = make_match()
        assert policy.decide(m) is None
        key = (m.park_id, m.map_id, m.start_date, m.nights)
        assert key in policy._seen
