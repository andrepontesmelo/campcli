from datetime import datetime

from campcli.clock import SystemClock


class TestSystemClock:
    def test_now_returns_current_datetime(self):
        before = datetime.now()
        result = SystemClock().now()
        after = datetime.now()
        assert before <= result <= after


class TestFrozenClock:
    def test_now_returns_frozen_value(self, clock):
        assert clock.now() == datetime(2026, 1, 1, 12, 0, 0)
