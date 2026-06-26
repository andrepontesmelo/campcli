"""Tests for search.run() with Profile model and allowed-park filtering."""
from __future__ import annotations

from datetime import date
from typing import Any
from unittest.mock import Mock

from campcli.domain.models import DriveTimes
from campcli.application.search import run as run_search
from campcli.domain.models import Map, Park, Profile, parse_pattern


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
    """Build a domain Profile. Patterns are parsed from string form."""
    defaults = dict(
        name="test",
        patterns=[parse_pattern("fri-sun")],
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
        profile = _make_profile()
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
        profile = _make_profile()
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
        profile = _make_profile()
        matches = list(
            run_search(api, profile, drive_times=_all_parks_drive_times(),
                       allowed_park_ids={1: None})
        )
        map_ids = {m.map_id for m in matches}
        assert map_ids == {10, 11}

    def test_allowed_empty_dict_is_noop(self) -> None:
        """Empty allowed_park_ids -> no parks matched (vacuous)."""
        api = _AvailabilityApi()
        profile = _make_profile()
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
            name="test",
            patterns=[parse_pattern("fri-sun")],
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
            name="test",
            patterns=[parse_pattern("mon-tue")],
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
            name="test",
            patterns=[parse_pattern("fri-mon:2-3")],
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
            name="test",
            patterns=[parse_pattern("fri-sun")],
            max_horizon_months=0,
        )
        windows = expand_windows(today, profile)
        assert windows == [(date(2025, 6, 13), 2)]

    def test_min_start_filters_emitted_starts(self) -> None:
        from campcli.application.search import expand_windows

        today = date(2025, 6, 13)  # Friday
        profile = Profile(
            name="test",
            patterns=[parse_pattern("fri-mon:2-3")],
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
            name="test",
            patterns=[parse_pattern("fri-mon:2-3")],
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
            name="test",
            patterns=[parse_pattern("fri-mon:2-3")],
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
            name="test",
            patterns=[parse_pattern("fri-mon:3-3")],
            max_horizon_months=0,
        )
        windows = expand_windows(today, profile)
        assert windows == [(date(2025, 6, 13), 3)]


class _SelectiveAvailabilityApi(_AvailabilityApi):
    """Fake API returning availability only for specific (park, map, start, nights)."""

    def __init__(
        self,
        available_stays: set[tuple[int, int, date, int]],
        parks: list[Park] | None = None,
    ) -> None:
        super().__init__(parks)
        self._available_stays = available_stays

    def map_availability(
        self, *, park_id: int, map_id: int, start: date, end: date, party_size: int = 1
    ) -> dict[int, list[dict[str, Any]]]:
        nights = (end - start).days
        if (park_id, map_id, start, nights) in self._available_stays:
            return {999: [{"date": start.isoformat(), "availability": 0}]}
        return {}


class TestPreferLongestDedup:
    """Prefer-longest dedup: longer stays suppress shorter overlapping stays."""

    def test_prefer_longest_dedup_3n_covers_2n(self) -> None:
        """fri-mon:2-3 — 3-night surfaces, 2-night suppressed."""
        api = _AvailabilityApi()
        profile = _make_profile(patterns=[parse_pattern("fri-mon:2-3")], max_horizon_months=0)
        today = date(2025, 6, 13)  # Friday
        matches = list(
            run_search(api, profile, drive_times=_all_parks_drive_times(), today=today)
        )
        assert len(matches) == 6  # 3 parks × 2 maps
        for m in matches:
            assert m.nights == 3
            assert m.start_date == date(2025, 6, 13)

    def test_prefer_longest_dedup_2n_covers_1n(self) -> None:
        """fri-mon:1-3 — only the 3-night surfaces per map (covers all smaller)."""
        api = _AvailabilityApi()
        profile = _make_profile(patterns=[parse_pattern("fri-mon:1-3")], max_horizon_months=0)
        today = date(2025, 6, 13)  # Friday
        matches = list(
            run_search(api, profile, drive_times=_all_parks_drive_times(), today=today)
        )
        assert len(matches) == 6
        for m in matches:
            assert m.nights == 3
            assert m.start_date == date(2025, 6, 13)

    def test_shorter_only_still_surfaces(self) -> None:
        """When 3-night check returns empty, the 2-night windows surface."""
        today = date(2025, 6, 13)  # Friday
        available: set[tuple[int, int, date, int]] = set()
        for park_id in (1, 2, 3):
            for map_id in (10, 11):
                available.add((park_id, map_id, date(2025, 6, 13), 2))
                available.add((park_id, map_id, date(2025, 6, 14), 2))
        api = _SelectiveAvailabilityApi(available)
        profile = _make_profile(patterns=[parse_pattern("fri-mon:2-3")])
        matches = list(
            run_search(api, profile, drive_times=_all_parks_drive_times(), today=today)
        )
        # Each map yields (Jun 13, 2) and (Jun 14, 2) — neither covers the other, both surface.
        assert len(matches) == 12  # 3 parks × 2 maps × 2 windows
        assert all(m.nights == 2 for m in matches)
        starts = {m.start_date for m in matches}
        assert starts == {date(2025, 6, 13), date(2025, 6, 14)}

    def test_disjoint_starts_both_yield(self) -> None:
        """Two distinct anchor Fridays — both independently yield."""
        today = date(2025, 6, 6)  # Friday
        available: set[tuple[int, int, date, int]] = {
            (1, 10, date(2025, 6, 6), 3),
            (1, 10, date(2025, 6, 13), 3),
        }
        api = _SelectiveAvailabilityApi(available)
        profile = _make_profile(patterns=[parse_pattern("fri-mon:2-3")], max_horizon_months=1)
        matches = list(
            run_search(api, profile, drive_times=_all_parks_drive_times(), today=today)
        )
        # Only park 1 / map 10 has availability; two disjoint anchors both surface.
        assert len(matches) == 2
        assert all(m.nights == 3 for m in matches)
        starts = {m.start_date for m in matches}
        assert starts == {date(2025, 6, 6), date(2025, 6, 13)}

    def test_regression_old_1n_2n_suppression_kept(self) -> None:
        """fri-sun:1-2 — 2-night covers both 1-night windows (adjacent + same-start)."""
        today = date(2025, 6, 13)  # Friday
        available: set[tuple[int, int, date, int]] = set()
        for park_id in (1, 2, 3):
            for map_id in (10, 11):
                available.add((park_id, map_id, date(2025, 6, 13), 2))
                available.add((park_id, map_id, date(2025, 6, 13), 1))
                available.add((park_id, map_id, date(2025, 6, 14), 1))
        api = _SelectiveAvailabilityApi(available)
        profile = _make_profile(patterns=[parse_pattern("fri-sun:1-2")])
        matches = list(
            run_search(api, profile, drive_times=_all_parks_drive_times(), today=today)
        )
        # Only the 2-night per map (covers Fri-1n and Sat-1n).
        assert len(matches) == 6
        for m in matches:
            assert m.nights == 2
            assert m.start_date == date(2025, 6, 13)


class TestExplosionGuard:
    """Explosion-guard warning fires / does not block / silent under threshold."""

    def test_explosion_warning_fires(self) -> None:
        """Pattern emitting >10 windows triggers progress warning."""
        from campcli.application.search import expand_windows

        today = date(2026, 6, 1)  # Monday
        profile = Profile(
            name="test",
            patterns=[parse_pattern("wed-mon:1-5")],
            max_horizon_months=2,
        )
        mock = Mock()
        windows = expand_windows(today, profile, warn=mock)
        assert len(windows) > 10  # sanity: the pattern is indeed explosive
        mock.assert_called_once()
        msg = mock.call_args[0][0]
        assert "warning" in msg.lower()

    def test_explosion_warning_does_not_block(self) -> None:
        """Even with explosive pattern, run() still yields matches."""
        api = _AvailabilityApi()
        profile = _make_profile(patterns=[parse_pattern("wed-mon:1-5")], max_horizon_months=2)
        today = date(2026, 6, 1)
        matches = list(
            run_search(
                api, profile, drive_times=_all_parks_drive_times(), today=today,
            )
        )
        assert len(matches) > 0

    def test_no_warning_under_threshold(self) -> None:
        """Bare pattern over a modest horizon does NOT trigger warning."""
        from campcli.application.search import expand_windows

        today = date(2026, 6, 1)  # Monday
        profile = Profile(
            name="test",
            patterns=[parse_pattern("fri-sun")],
            max_horizon_months=1,
        )
        mock = Mock()
        windows = expand_windows(today, profile, warn=mock)
        assert 0 < len(windows) < 10  # well under threshold
        mock.assert_not_called()


class TestBackwardCompat:
    """Backward-compatibility regression lock for the migration promise."""

    def test_bare_fri_sun_unchanged(self) -> None:
        """Profile with ['fri-sun'] yields identical matches to ['fri-sun:2-2']."""
        api = _AvailabilityApi()
        today = date(2026, 6, 1)

        profile_bare = _make_profile(patterns=[parse_pattern("fri-sun")])
        profile_explicit = _make_profile(patterns=[parse_pattern("fri-sun:2-2")])

        matches_bare = list(
            run_search(
                api, profile_bare, drive_times=_all_parks_drive_times(), today=today,
            )
        )
        matches_explicit = list(
            run_search(
                api, profile_explicit, drive_times=_all_parks_drive_times(), today=today,
            )
        )
        set_bare = set((m.start_date, m.nights) for m in matches_bare)
        set_explicit = set((m.start_date, m.nights) for m in matches_explicit)
        assert set_bare == set_explicit
