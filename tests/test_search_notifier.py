from datetime import date
from unittest.mock import Mock

from campcli.application.drive_times import DriveTimes
from campcli.application.search_notifier import SearchNotifier
from campcli.domain.models import WeekendMatch


class FakeTelegram:
    def __init__(self):
        self.sent: list[str] = []

    def send_to(self, chat_id: str, text: str) -> int:
        self.sent.append(text)
        return len(self.sent)


def _empty_repo():
    repo = Mock()
    repo.load_skip_set.return_value = set()
    return repo


def make_notifier(not_interested_repo=None):
    return SearchNotifier(
        telegram=FakeTelegram(),
        drive_times=DriveTimes.empty(),
        log=lambda msg: None,
        not_interested_repo=not_interested_repo or _empty_repo(),
    )


def make_match(**kw):
    defaults = dict(
        park_id=1, park_name="Bowron Lake", map_id=10, map_name="Main",
        start_date=date(2026, 8, 15), end_date=date(2026, 8, 17),
        nights=2, available_count=1,
    )
    defaults.update(kw)
    return WeekendMatch(**defaults)


class TestSearchNotifierDedup:
    def test_same_match_notified_twice_sends_once(self):
        notifier = make_notifier()
        m = make_match()
        notifier.start_poll([], set(), profile_id=1)
        notifier.notify(m, chat_ids=["chat1"])
        notifier.notify(m, chat_ids=["chat1"])
        assert len(notifier._telegram.sent) == 1

    def test_different_match_sends_twice(self):
        notifier = make_notifier()
        m1 = make_match(park_id=1)
        m2 = make_match(park_id=2)
        notifier.start_poll([], set(), profile_id=1)
        notifier.notify(m1, chat_ids=["chat1"])
        notifier.notify(m2, chat_ids=["chat1"])
        assert len(notifier._telegram.sent) == 2


class TestSearchNotifierBlocked:
    def test_blocked_park_suppresses_notification(self):
        notifier = make_notifier()
        m = make_match()
        notifier.start_poll([], {1}, profile_id=1)
        notifier.notify(m, chat_ids=["chat1"])
        assert len(notifier._telegram.sent) == 0

    def test_blocked_match_key_added_to_seen(self):
        notifier = make_notifier()
        m = make_match()
        notifier.start_poll([], {1}, profile_id=1)
        notifier.notify(m, chat_ids=["chat1"])
        key = (m.park_id, m.map_id, m.start_date, m.nights)
        assert key in notifier._policy._seen


class TestSearchNotifierBroadcast:
    def test_broadcast_to_multiple_chats(self):
        notifier = make_notifier()
        m = make_match()
        notifier.start_poll([], set(), profile_id=1)
        notifier.notify(m, chat_ids=["chat1", "chat2"])
        assert len(notifier._telegram.sent) == 2

    def test_empty_chat_ids_sends_nothing(self):
        notifier = make_notifier()
        m = make_match()
        notifier.start_poll([], set(), profile_id=1)
        notifier.notify(m, chat_ids=[])
        assert len(notifier._telegram.sent) == 0


class TestSearchNotifierNotInterested:
    def test_skip_set_drops_match_before_policy(self):
        """Match in skip set is silently dropped — no notification, no record_sent."""
        repo = Mock()
        repo.load_skip_set.return_value = {(1, date(2026, 8, 15), date(2026, 8, 17))}
        notifier = make_notifier(not_interested_repo=repo)
        m = make_match()
        notifier.start_poll([], set(), profile_id=1)
        notifier.notify(m, chat_ids=["chat1"])
        assert len(notifier._telegram.sent) == 0
        repo.record_sent.assert_not_called()

    def test_skip_set_allows_non_matching(self):
        """Match NOT in skip set is notified normally."""
        repo = Mock()
        repo.load_skip_set.return_value = {(2, date(2026, 8, 20), date(2026, 8, 22))}
        notifier = make_notifier(not_interested_repo=repo)
        m = make_match()
        notifier.start_poll([], set(), profile_id=1)
        notifier.notify(m, chat_ids=["chat1"])
        assert len(notifier._telegram.sent) == 1

    def test_record_sent_called_after_successful_send(self):
        repo = Mock()
        repo.load_skip_set.return_value = set()
        notifier = make_notifier(not_interested_repo=repo)
        m = make_match()
        notifier.start_poll([], set(), profile_id=1)
        notifier.notify(m, chat_ids=["chat1"])
        repo.record_sent.assert_called_once()
        call_kwargs = repo.record_sent.call_args
        assert call_kwargs[1]["profile_id"] == 1
        assert call_kwargs[1]["park_id"] == 1

    def test_record_sent_not_called_when_match_skipped(self):
        repo = Mock()
        repo.load_skip_set.return_value = {(1, date(2026, 8, 15), date(2026, 8, 17))}
        notifier = make_notifier(not_interested_repo=repo)
        m = make_match()
        notifier.start_poll([], set(), profile_id=1)
        notifier.notify(m, chat_ids=["chat1"])
        repo.record_sent.assert_not_called()
