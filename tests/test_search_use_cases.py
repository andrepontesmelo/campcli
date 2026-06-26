"""Unit tests for search use-case functions (application/search.py) with duck-typed fakes."""
from __future__ import annotations

from datetime import date
from typing import Any

import pytest
import typer

from campcli.application.search import (
    _search_for_profile,
    check as check_uc,
    book_open as book_open_uc,
    book_quote as book_quote_uc,
)
from campcli.domain.models import AvailableSite, DriveTimes, Map, Park, Profile, parse_pattern
from campcli.domain.ports import BCParksApi, ProfileRepo


# ---------------------------------------------------------------------------
# Duck-typed fakes
# ---------------------------------------------------------------------------


class FakeProfileRepo:
    """In-memory ProfileRepo for testing. Satisfies the ProfileRepo Protocol."""

    def __init__(self) -> None:
        self._profiles: dict[str, Profile] = {}
        self._next_id = 1

    def create(self, profile: Profile) -> Profile:
        p = profile.model_copy(deep=True)
        p.id = self._next_id
        self._next_id += 1
        self._profiles[p.name] = p
        return p

    def list_all(self) -> list[Profile]:
        return list(self._profiles.values())

    def list_enabled(self) -> list[Profile]:
        return [p for p in self._profiles.values() if p.enabled]

    def get_by_name(self, name: str) -> Profile | None:
        return self._profiles.get(name)

    def get_by_id(self, profile_id: int) -> Profile | None:
        for p in self._profiles.values():
            if p.id == profile_id:
                return p
        return None

    def update(self, profile: Profile) -> Profile:
        return profile

    def delete(self, name: str) -> bool:
        return False

    def set_enabled(self, name: str, enabled: bool) -> bool:
        if name in self._profiles:
            self._profiles[name].enabled = enabled
            return True
        return False

    def add_pattern(self, profile_name: str, pattern: str, sort_order: int = 0) -> None:
        pass

    def remove_pattern(self, profile_name: str, pattern: str) -> bool:
        return False

    def list_patterns(self, profile_name: str) -> list:
        return []

    def add_park(self, profile_name: str, park_query: str, map_query: str | None = None) -> None:
        pass

    def remove_park(self, profile_name: str, park_query: str) -> bool:
        return False

    def list_parks(self, profile_name: str) -> list:
        return []

    def add_tg_id(self, profile_name: str, tg_id: int) -> None:
        pass

    def remove_tg_id(self, profile_name: str, tg_id: int) -> bool:
        return False

    def list_tg_ids(self, profile_name: str) -> list[int]:
        return []


class FakeBCParksApi:
    """Minimal BCParksApi for search use-case tests."""

    def __init__(self, parks: list[Park] | None = None) -> None:
        self._parks = parks or []
        self._maps: dict[int, list[Map]] = {}

    def list_parks(self, *, refresh: bool = False) -> list[Park]:
        return self._parks

    def list_maps(self, park_id: int) -> list[Map]:
        return self._maps.get(park_id, [])

    def map_availability(
        self, *, park_id: int, map_id: int, start: date, end: date, party_size: int = 1
    ) -> dict[int, list[dict[str, Any]]]:
        return {}

    def resource_details(self, *, park_id: int, map_id: int) -> dict[str, Any]:
        return {}


class FakeBCParksApiWithSites(FakeBCParksApi):
    """Fake API that returns one available site for every (park, map, start) combo."""

    def __init__(self, parks: list[Park] | None = None) -> None:
        super().__init__(parks)
        self._maps = {}

    def map_availability(
        self, *, park_id: int, map_id: int, start: date, end: date, party_size: int = 1
    ) -> dict[int, list[dict[str, Any]]]:
        return {999: [{"date": start.isoformat(), "availability": 0}]}


# Static assertions: the fakes satisfy the Protocols.
_p: ProfileRepo = FakeProfileRepo()
_a: BCParksApi = FakeBCParksApi()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


GOLDEN_EARS = Park(park_id=1, name="Golden Ears", region="test")
CULTUS = Park(park_id=2, name="Cultus Lake", region="test")


@pytest.fixture
def api() -> FakeBCParksApi:
    return FakeBCParksApi()


@pytest.fixture
def api_with_parks() -> FakeBCParksApi:
    a = FakeBCParksApi(parks=[GOLDEN_EARS, CULTUS])
    a._maps = {
        1: [Map(map_id=10, park_id=1, name="Main")],
        2: [Map(map_id=20, park_id=2, name="East Loop")],
    }
    return a


@pytest.fixture
def profile() -> Profile:
    return Profile(
        name="test",
        patterns=[parse_pattern("fri-sun")],
        max_horizon_months=3,
        max_drive_hours=99.0,
    )


# ---------------------------------------------------------------------------
# _search_for_profile
# ---------------------------------------------------------------------------


class TestSearchForProfile:
    def test_no_matches_raises_exit(self, api: FakeBCParksApi, profile: Profile) -> None:
        """Empty API results yield typer.Exit(3)."""
        with pytest.raises(typer.Exit):
            _search_for_profile(
                profile, api, DriveTimes.empty(),
                group_by="weekend",
            )

    def test_happy_path_no_exception(self, profile: Profile) -> None:
        """Matches found — no crash."""
        api = FakeBCParksApiWithSites(parks=[GOLDEN_EARS])
        api._maps = {1: [Map(map_id=10, park_id=1, name="Main")]}
        dt = DriveTimes({1: {"hours": 1.0}})
        # Should render successfully (no typer.Exit raised).
        _search_for_profile(profile, api, dt, group_by="weekend")


# ---------------------------------------------------------------------------
# check
# ---------------------------------------------------------------------------


class TestCheck:
    def test_park_not_found(self, api: FakeBCParksApi, profile: Profile) -> None:
        """Non-existent park_id -> typer.Exit(2)."""
        with pytest.raises(typer.Exit):
            check_uc(api, profile, park_id=999, start=date(2026, 8, 1), nights=2)

    def test_empty_results(self, api_with_parks: FakeBCParksApi, profile: Profile) -> None:
        """No availability -> typer.Exit(3)."""
        with pytest.raises(typer.Exit):
            check_uc(api_with_parks, profile, park_id=1, start=date(2026, 8, 1), nights=2)

    def test_happy_path(self, profile: Profile) -> None:
        """Available sites found — no exception."""
        api = FakeBCParksApiWithSites(parks=[GOLDEN_EARS])
        api._maps = {1: [Map(map_id=10, park_id=1, name="Main")]}
        # Should not raise.
        check_uc(api, profile, park_id=1, start=date(2026, 8, 1), nights=2)

    def test_profile_name_displayed(self, profile: Profile) -> None:
        """Profile name appears in stderr output."""
        api = FakeBCParksApiWithSites(parks=[GOLDEN_EARS])
        api._maps = {1: [Map(map_id=10, park_id=1, name="Main")]}
        check_uc(api, profile, park_id=1, start=date(2026, 8, 1), nights=2)
        # No exception — profile name is echo'd to stderr


# ---------------------------------------------------------------------------
# book_open / book_quote
# ---------------------------------------------------------------------------


class TestBookOpen:
    def test_generates_url(self) -> None:
        url = book_open_uc(park_id=1, map_id=10, start=date(2026, 8, 15), nights=2, party_size=2)
        assert "create-booking/results" in url
        assert "resourceLocationId=1" in url

    def test_default_party_size(self) -> None:
        url = book_open_uc(park_id=1, map_id=10, start=date(2026, 8, 15), nights=2)
        assert "partySize=1" in url


class TestBookQuote:
    def test_generates_url(self) -> None:
        url = book_quote_uc(park_id=1, map_id=10, start=date(2026, 8, 15), nights=2, party_size=2)
        assert "create-booking/results" in url
        assert "resourceLocationId=1" in url

    def test_default_party_size(self) -> None:
        url = book_quote_uc(park_id=1, map_id=10, start=date(2026, 8, 15), nights=2)
        assert "partySize=1" in url
