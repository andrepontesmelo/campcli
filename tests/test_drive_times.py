"""Unit tests for DriveTimes value object — no fixtures needed, just a dict."""
from campcli.application.drive_times import DriveTimes


class TestHoursFor:
    def test_returns_hours_for_present_park(self):
        dt = DriveTimes({1: {"lat": 50, "lon": -120, "hours": 3.5}})
        assert dt.hours_for(1) == 3.5

    def test_returns_none_for_absent_park(self):
        dt = DriveTimes({1: {"lat": 50, "lon": -120, "hours": 3.5}})
        assert dt.hours_for(999) is None

    def test_returns_none_when_hours_is_null(self):
        dt = DriveTimes({1: {"lat": None, "lon": None, "hours": None}})
        assert dt.hours_for(1) is None


class TestIsWithin:
    def test_within_threshold(self):
        dt = DriveTimes({1: {"lat": 50, "lon": -120, "hours": 2.0}})
        assert dt.is_within(1, 3.0) is True

    def test_exactly_at_threshold(self):
        dt = DriveTimes({1: {"lat": 50, "lon": -120, "hours": 3.0}})
        assert dt.is_within(1, 3.0) is True

    def test_over_threshold(self):
        dt = DriveTimes({1: {"lat": 50, "lon": -120, "hours": 4.0}})
        assert dt.is_within(1, 3.0) is False

    def test_absent_park_returns_false(self):
        dt = DriveTimes({1: {"lat": 50, "lon": -120, "hours": 2.0}})
        assert dt.is_within(999, 3.0) is False

    def test_null_hours_returns_false(self):
        dt = DriveTimes({1: {"lat": None, "lon": None, "hours": None}})
        assert dt.is_within(1, 3.0) is False


class TestBool:
    def test_empty_is_falsy(self):
        assert bool(DriveTimes({})) is False

    def test_populated_is_truthy(self):
        assert bool(DriveTimes({1: {"lat": 50, "lon": -120, "hours": 3.5}})) is True

    def test_empty_classmethod_returns_falsy(self):
        assert bool(DriveTimes.empty()) is False
