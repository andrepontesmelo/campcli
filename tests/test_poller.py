from datetime import date

from campcli import store
from campcli.models import WeekendMatch
from campcli.ports import TelegramUpdate


class TestPollerStart:
    def test_start_sends_startup_message(self, poller, fake_telegram):
        poller.start()
        assert "campcli daemon started v3" in " ".join(fake_telegram.sent)


class TestPollerCommands:
    def test_verbose_on(self, poller, fake_telegram, tmp_db):
        fake_telegram.canned_updates = [
            TelegramUpdate(update_id=1, chat_id="1", text="/verbose on")
        ]
        poller.tick()
        assert poller._verbose is True
        assert store.get_setting("verbose") == "on"
        assert "verbose logging ON" in fake_telegram.sent

    def test_verbose_off(self, poller, fake_telegram, tmp_db):
        store.set_setting("verbose", "on")
        fake_telegram.canned_updates = [
            TelegramUpdate(update_id=1, chat_id="1", text="/verbose off")
        ]
        poller.tick()
        assert poller._verbose is False
        assert store.get_setting("verbose") == "off"
        assert "verbose logging OFF" in fake_telegram.sent

    def test_unknown_command(self, poller, fake_telegram, tmp_db):
        fake_telegram.canned_updates = [
            TelegramUpdate(update_id=1, chat_id="1", text="garbage")
        ]
        poller.tick()
        assert poller._verbose is False  # unchanged


class TestPollerDedup:
    # Dedup test exercises dedup in isolation.
    # Filter integration (blocked/booking-adjacent) tested in TestPollerBlocked
    # and filters.should_notify tests.
    def test_same_match_dispatched_twice_sends_once(self, poller, fake_telegram):
        m = WeekendMatch(
            park_id=1, park_name="Bowron Lake", map_id=10, map_name="Main",
            start_date=date(2026, 8, 15), end_date=date(2026, 8, 17),
            nights=2, available_count=1,
        )
        poller._dispatch_match(m, [], set(), {})
        assert len(fake_telegram.sent) == 1
        poller._dispatch_match(m, [], set(), {})
        assert len(fake_telegram.sent) == 1  # deduped


class TestPollerBlocked:
    def test_blocked_park_suppresses_notification(self, poller, fake_telegram, tmp_db):
        store.add_blocked_park(1, "Bowron Lake")
        m = WeekendMatch(
            park_id=1, park_name="Bowron Lake", map_id=10, map_name="Main",
            start_date=date(2026, 8, 15), end_date=date(2026, 8, 17),
            nights=2, available_count=1,
        )
        poller._dispatch_match(m, [], {1}, {})
        assert len(fake_telegram.sent) == 0
        key = (m.park_id, m.map_id, m.start_date, m.nights)
        assert key in poller._seen
