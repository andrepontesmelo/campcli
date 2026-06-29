"""Tests for application/search_loop.py — module-level ``run_search_once``.

These tests verify multi-profile dedup, fan-out, and notification isolation
by calling the function directly instead of through ``Poller``.
"""
from __future__ import annotations

from datetime import date

from campcli.domain.models import Profile
from conftest import FakeBCParksApi, FakeSearchNotifier


def _run(
    *,
    api=None,
    profile_repo=None,
    settings_repo=None,
    drive_times=None,
    not_interested_repo=None,
    clock=None,
    notifier_factory=None,
    notifiers=None,
    log=None,
):
    """Convenience wrapper: build defaults then call run_search_once."""
    from campcli.application.search_loop import run_search_once
    from campcli.domain.models import DriveTimes

    run_search_once(
        api=api,
        profile_repo=profile_repo,
        settings_repo=settings_repo,
        drive_times=drive_times or DriveTimes.empty(),
        not_interested_repo=not_interested_repo,
        clock=clock,
        notifier_factory=notifier_factory or (lambda p: FakeSearchNotifier()),
        notifiers=notifiers or {},
        log=log or (lambda *a: None),
    )


# ---------------------------------------------------------------------------
# Multi-profile dedup tests
# ---------------------------------------------------------------------------


class TestMultiProfileDedup:
    def test_empty_profiles_no_api_calls(self, fake_api, profile_repo):
        """No enabled profiles → no API calls."""
        _run(api=fake_api, profile_repo=profile_repo, settings_repo=profile_repo)
        assert len(fake_api.map_availability_calls) == 0

    def test_single_profile_calls_api(self, fake_api, profile_repo):
        """Single profile with a park triggers one API call per (park, map)."""
        p = profile_repo.create(Profile(name="test", max_horizon_months=3))
        profile_repo.add_pattern("test", "fri-sun")
        profile_repo.add_park("test", "Bowron Lake")
        _run(api=fake_api, profile_repo=profile_repo, settings_repo=profile_repo)
        # Bowron Lake (park_id=1) has 1 non-walk-in map (map_id=10)
        assert len(fake_api.map_availability_calls) == 1
        assert fake_api.map_availability_calls[0][:2] == (1, 10)

    def test_two_profiles_same_park_dedup(self, fake_api, profile_repo):
        """Two profiles watching the same park → API called once per (park, map) pair."""
        p1 = profile_repo.create(Profile(name="p1", max_horizon_months=3))
        profile_repo.add_pattern("p1", "fri-sun")
        profile_repo.add_park("p1", "Bowron Lake")

        p2 = profile_repo.create(Profile(name="p2", max_horizon_months=3))
        profile_repo.add_pattern("p2", "fri-sun")
        profile_repo.add_park("p2", "Bowron Lake")

        _run(api=fake_api, profile_repo=profile_repo, settings_repo=profile_repo)
        # One unique (park, map) pair → one API call
        assert len(fake_api.map_availability_calls) == 1
        assert fake_api.map_availability_calls[0][:2] == (1, 10)

    def test_two_profiles_different_parks(self, fake_api, profile_repo):
        """Two profiles watching different parks → one API call per unique pair."""
        p1 = profile_repo.create(Profile(name="p1", max_horizon_months=3))
        profile_repo.add_pattern("p1", "fri-sun")
        profile_repo.add_park("p1", "Bowron Lake")  # park_id=1

        p2 = profile_repo.create(Profile(name="p2", max_horizon_months=3))
        profile_repo.add_pattern("p2", "fri-sun")
        profile_repo.add_park("p2", "Golden Ears")  # park_id=2

        _run(api=fake_api, profile_repo=profile_repo, settings_repo=profile_repo)
        # Two unique (park, map) pairs → two API calls
        parks_called = {c[0] for c in fake_api.map_availability_calls}
        assert parks_called == {1, 2}
        assert len(fake_api.map_availability_calls) == 2

    def test_disabled_profile_skipped(self, fake_api, profile_repo):
        """A disabled profile is not loaded and its park is not checked."""
        p = profile_repo.create(
            Profile(name="disabled", max_horizon_months=3, enabled=False)
        )
        profile_repo.add_pattern("disabled", "fri-sun")
        profile_repo.add_park("disabled", "Bowron Lake")

        _run(api=fake_api, profile_repo=profile_repo, settings_repo=profile_repo)
        assert len(fake_api.map_availability_calls) == 0


# ---------------------------------------------------------------------------
# Fan-out and per-profile TG isolation tests
# ---------------------------------------------------------------------------


class TestFanOut:
    def test_per_profile_tg_isolation(self, store, clock, fake_telegram, profile_repo):
        """Each profile's notify receives only its own tg_allowed_ids chat_ids."""
        from campcli.application.search_loop import run_search_once
        from campcli.domain.models import DriveTimes

        # Two profiles with disjoint tg_allowed_ids, same park.
        p100 = profile_repo.create(
            Profile(name="p100", max_horizon_months=3, tg_allowed_ids=[100])
        )
        profile_repo.add_tg_id("p100", 100)
        profile_repo.add_pattern("p100", "fri-sun")
        profile_repo.add_park("p100", "Bowron Lake")

        p200 = profile_repo.create(
            Profile(name="p200", max_horizon_months=3, tg_allowed_ids=[200])
        )
        profile_repo.add_tg_id("p200", 200)
        profile_repo.add_pattern("p200", "fri-sun")
        profile_repo.add_park("p200", "Bowron Lake")

        store.set_setting("chat:100", "chat_a")
        store.set_setting("chat:200", "chat_b")

        # Date.today() is used — produce a matching slot.
        today = date.today()
        days_until_friday = (4 - today.weekday()) % 7
        first_friday = today + __import__("datetime").timedelta(days=days_until_friday)

        class RichApi(FakeBCParksApi):
            def map_availability(
                self, *, park_id, map_id, start, end, party_size=1, daily=False
            ):
                super().map_availability(
                    park_id=park_id, map_id=map_id, start=start, end=end,
                    party_size=party_size, daily=daily,
                )
                # Positional daily grid (index i == night start + i). Reserve
                # every night except first_friday's fri-sun (2-night) window.
                n = (end - start).days
                off = (first_friday - start).days
                grid = [{"availability": 1} for _ in range(n)]
                for i in (off, off + 1):
                    if 0 <= i < n:
                        grid[i] = {"availability": 0}
                return {101: grid}

        api = RichApi()

        # Recording notifier — all calls land in one shared list.
        notify_records: list[tuple[str, list[str]]] = []

        class _Recorder(FakeSearchNotifier):
            def __init__(self, profile_name: str) -> None:
                super().__init__()
                self._profile_name = profile_name

            def notify(self, match, *, chat_ids=None):
                super().notify(match, chat_ids=chat_ids)
                notify_records.append(
                    (self._profile_name, list(chat_ids) if chat_ids else [])
                )

        def _factory(profile):
            return _Recorder(profile.name)

        run_search_once(
            api=api,
            profile_repo=profile_repo,
            settings_repo=store,
            drive_times=DriveTimes.empty(),
            not_interested_repo=store,
            clock=clock,
            notifier_factory=_factory,
            notifiers={},
            log=lambda *a: None,
        )

        assert len(notify_records) == 2
        # p100 gets only chat_a
        assert ("p100", ["chat_a"]) in notify_records
        assert ("p100", ["chat_b"]) not in notify_records
        # p200 gets only chat_b
        assert ("p200", ["chat_b"]) in notify_records
        assert ("p200", ["chat_a"]) not in notify_records

    def test_fan_out_order(self, store, clock, fake_telegram, profile_repo):
        """All notifications for park A complete before any API call for park B."""
        from campcli.application.search_loop import run_search_once
        from campcli.domain.models import DriveTimes

        # p_a: Bowron Lake (park 1) + Golden Ears (park 2)
        # p_b: Bowron Lake (park 1) only
        # disabled: ignored
        p_a = profile_repo.create(
            Profile(name="p_a", max_horizon_months=3)
        )
        profile_repo.add_pattern("p_a", "fri-sun")
        profile_repo.add_park("p_a", "Bowron Lake")
        profile_repo.add_park("p_a", "Golden Ears")

        p_b = profile_repo.create(
            Profile(name="p_b", max_horizon_months=3)
        )
        profile_repo.add_pattern("p_b", "fri-sun")
        profile_repo.add_park("p_b", "Bowron Lake")

        profile_repo.create(
            Profile(name="c", max_horizon_months=3, enabled=False)
        )
        profile_repo.add_pattern("c", "fri-sun")
        profile_repo.add_park("c", "Bowron Lake")

        # Date.today() is used — produce a matching slot.
        today = date.today()
        days_until_friday = (4 - today.weekday()) % 7
        first_friday = today + __import__("datetime").timedelta(days=days_until_friday)

        class RichApi(FakeBCParksApi):
            def map_availability(
                self, *, park_id, map_id, start, end, party_size=1, daily=False
            ):
                super().map_availability(
                    park_id=park_id, map_id=map_id, start=start, end=end,
                    party_size=party_size, daily=daily,
                )
                # Positional daily grid (index i == night start + i). Reserve
                # every night except first_friday's fri-sun (2-night) window.
                n = (end - start).days
                off = (first_friday - start).days
                grid = [{"availability": 1} for _ in range(n)]
                for i in (off, off + 1):
                    if 0 <= i < n:
                        grid[i] = {"availability": 0}
                return {101: grid}

        api = RichApi()

        # Recording notifier — records (profile_name, park_name) per notify.
        notify_order: list[tuple[str, str]] = []

        class _OrderRecorder(FakeSearchNotifier):
            def __init__(self, profile) -> None:
                super().__init__()
                self._profile = profile

            def notify(self, match, *, chat_ids=None):
                super().notify(match, chat_ids=chat_ids)
                notify_order.append((self._profile.name, match.park_name))

        def _factory(profile):
            return _OrderRecorder(profile)

        run_search_once(
            api=api,
            profile_repo=profile_repo,
            settings_repo=store,
            drive_times=DriveTimes.empty(),
            not_interested_repo=store,
            clock=clock,
            notifier_factory=_factory,
            notifiers={},
            log=lambda *a: None,
        )

        # pair_to_profiles order: (1, 10) → [p_a, p_b], (2, 10) → [p_a]
        # Expected notify_order: p_a/Bowron, p_b/Bowron, p_a/Golden Ears
        assert len(notify_order) == 3
        assert notify_order[0] == ("p_a", "Bowron Lake")
        assert notify_order[1] == ("p_b", "Bowron Lake")
        assert notify_order[2] == ("p_a", "Golden Ears")

        # map_availability_calls: park 1 before park 2
        assert len(api.map_availability_calls) >= 2
        assert api.map_availability_calls[0][0] == 1  # Bowron Lake
        assert api.map_availability_calls[1][0] == 2  # Golden Ears
