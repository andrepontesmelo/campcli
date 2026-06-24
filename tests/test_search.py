"""Tests for search.run() with Profile model and allowed-park filtering."""
from __future__ import annotations

from datetime import date
from typing import Any

from campcli.application.drive_times import DriveTimes
from campcli.application.profile import Profile
from campcli.application.search import run as run_search
from campcli.domain.models import Map, Park


class _AvailabilityApi:
    """Fake API that returns one available site for every (park, map, start) combo."""

    def __init__(self, parks: list[Park] | None = None) -> None:
        self._parks = parks or [
            Park(park_id=1, name="Cultus Lake", region="test"),
            Park(park_id=2, name="Golden Ears", region="test"),
            Park(park_id=3, name="Bowron Lake", region="test"),
        ]

    def list_parks(self, *, refresh: bool = False) -> list[Park]:
        return self._parks

    def list_maps(self, park_id: int) -> list[Map]:
        return [
            Map(map_id=10, park_id=park_id, name="Main"),
            Map(map_id=11, park_id=park_id, name="East Loop"),
        ]

    def map_availability(
        self, *, park_id: int, map_id: int, start: date, end: date, party_size: int = 1
    ) -> dict[int, list[dict[str, Any]]]:
        # Return one available site for every request.
        return {999: [{"date": start.isoformat(), "availability": 0}]}

    def resource_details(self, *, park_id: int, map_id: int) -> dict[str, Any]:
        return {}


def _make_profile(**kw) -> Profile:
    defaults = dict(
        patterns=["fri-sun"],
        max_horizon_months=3,
        max_drive_hours=99.0,  # allow all parks
    )
    defaults.update(kw)
    return Profile(**defaults)


def _all_parks_drive_times() -> DriveTimes:
    """DriveTimes where all test parks are within range."""
    return DriveTimes({
        1: {"hours": 1.0},
        2: {"hours": 2.0},
        3: {"hours": 0.5},
    })


class TestSearchRunWithAllowed:
    def test_empty_allowed_returns_all_parks(self) -> None:
        """allowed_park_ids=None -> all parks within drive range checked."""
        api = _AvailabilityApi()
        profile = _make_profile()
        matches = list(
            run_search(api, profile, drive_times=_all_parks_drive_times())
        )
        # All non-walk-in maps yield matches with the fake API.
        assert len(matches) > 0
        park_ids = {m.park_id for m in matches}
        assert park_ids == {1, 2, 3}

    def test_allowed_park_ids_filters_parks(self) -> None:
        """Only the allowed park is searched."""
        api = _AvailabilityApi()
        profile = _make_profile(allowed_park_ids={1: None})
        matches = list(
            run_search(api, profile, drive_times=_all_parks_drive_times(),
                       allowed_park_ids={1: None})
        )
        assert len(matches) > 0
        park_ids = {m.park_id for m in matches}
        assert park_ids == {1}

    def test_allowed_park_ids_filters_maps(self) -> None:
        """Only the allowed map within a park is searched."""
        api = _AvailabilityApi()
        profile = _make_profile(allowed_park_ids={1: {10}})
        matches = list(
            run_search(api, profile, drive_times=_all_parks_drive_times(),
                       allowed_park_ids={1: {10}})
        )
        assert len(matches) > 0
        for m in matches:
            assert m.park_id == 1
            assert m.map_id == 10

    def test_allowed_none_means_all_maps(self) -> None:
        """allowed_park_ids with None map set means all maps."""
        api = _AvailabilityApi()
        profile = _make_profile(allowed_park_ids={1: None})
        matches = list(
            run_search(api, profile, drive_times=_all_parks_drive_times(),
                       allowed_park_ids={1: None})
        )
        map_ids = {m.map_id for m in matches}
        assert map_ids == {10, 11}

    def test_allowed_empty_dict_is_noop(self) -> None:
        """Empty allowed_park_ids -> no parks matched (vacuous)."""
        api = _AvailabilityApi()
        profile = _make_profile(allowed_park_ids={})
        matches = list(
            run_search(api, profile, drive_times=_all_parks_drive_times(),
                       allowed_park_ids={})
        )
        assert len(matches) == 0


class TestExpandWindowsMinStart:
    def test_min_start_filters_early_windows(self) -> None:
        """min_start_date in profile skips windows before that date."""
        from campcli.application.search import expand_windows

        today = date(2026, 6, 1)
        profile = Profile(
            patterns=["fri-sun"],
            max_horizon_months=1,
            min_start_date="2026-06-10",
        )
        windows = expand_windows(
            today, profile,
            min_start=date(2026, 6, 10),
        )
        assert all(w[0] >= date(2026, 6, 10) for w in windows)

    def test_no_min_start_uses_today(self) -> None:
        """When min_start_date is None, expand from today."""
        from campcli.application.search import expand_windows

        today = date(2026, 6, 15)
        profile = Profile(
            patterns=["mon-tue"],
            max_horizon_months=1,
            min_start_date=None,
        )
        windows = expand_windows(today, profile)
        assert all(w[0] >= today for w in windows)


class TestExpandWindowsEnumeration:
    def test_ranged_pattern_fri_mon_2_3(self) -> None:
        from campcli.application.search import expand_windows

        today = date(2025, 6, 13)  # Friday
        profile = Profile(
            patterns=["fri-mon:2-3"],
            max_horizon_months=0,
        )
        windows = expand_windows(today, profile)
        assert set(windows) == {
            (date(2025, 6, 13), 2),
            (date(2025, 6, 14), 2),
            (date(2025, 6, 13), 3),
        }

    def test_bare_pattern_unchanged(self) -> None:
        from campcli.application.search import expand_windows

        today = date(2025, 6, 13)  # Friday
        profile = Profile(
            patterns=["fri-sun"],
            max_horizon_months=0,
        )
        windows = expand_windows(today, profile)
        assert windows == [(date(2025, 6, 13), 2)]

    def test_min_start_filters_emitted_starts(self) -> None:
        from campcli.application.search import expand_windows

        today = date(2025, 6, 13)  # Friday
        profile = Profile(
            patterns=["fri-mon:2-3"],
            max_horizon_months=0,
        )
        windows = expand_windows(
            today, profile,
            min_start=date(2025, 6, 14),
        )
        assert windows == [(date(2025, 6, 14), 2)]

    def test_max_start_filters_emitted_starts(self) -> None:
        from campcli.application.search import expand_windows

        today = date(2025, 6, 13)  # Friday
        profile = Profile(
            patterns=["fri-mon:2-3"],
            max_horizon_months=0,
        )
        windows = expand_windows(
            today, profile,
            max_start=date(2025, 6, 13),
        )
        assert set(windows) == {
            (date(2025, 6, 13), 2),
            (date(2025, 6, 13), 3),
        }

    def test_past_date_anchor_excluded(self) -> None:
        from campcli.application.search import expand_windows

        today = date(2025, 6, 14)  # Saturday
        profile = Profile(
            patterns=["fri-mon:2-3"],
            max_horizon_months=1,
        )
        windows = expand_windows(today, profile)
        first_friday = date(2025, 6, 20)
        assert all(w[0] >= today for w in windows)
        assert all(w[0] >= first_friday for w in windows)

    def test_min_equals_max_equals_span(self) -> None:
        from campcli.application.search import expand_windows

        today = date(2025, 6, 13)  # Friday
        profile = Profile(
            patterns=["fri-mon:3-3"],
            max_horizon_months=0,
        )
        windows = expand_windows(today, profile)
        assert windows == [(date(2025, 6, 13), 3)]
