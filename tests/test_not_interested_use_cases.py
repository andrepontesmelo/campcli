"""Unit tests for not-interested use-case functions (application/not_interested.py) with duck-typed fakes."""
from __future__ import annotations

from datetime import date

import pytest
import typer

from campcli.application.not_interested import (
    not_interested_add,
    not_interested_list,
    not_interested_rm,
)
from campcli.domain.models import NotInterested, Park, Profile
from campcli.domain.ports import BCParksApi, NotInterestedRepo, ProfileRepo


# ---------------------------------------------------------------------------
# Duck-typed fakes
# ---------------------------------------------------------------------------


class FakeNotInterestedRepo:
    """In-memory NotInterestedRepo for testing. Satisfies the NotInterestedRepo Protocol."""

    def __init__(self) -> None:
        self._entries: list[NotInterested] = []

    def add(self, profile_id: int, park_id: int, date_start: date, date_end: date) -> None:
        for e in self._entries:
            if (
                e.profile_id == profile_id
                and e.park_id == park_id
                and e.date_start == date_start
                and e.date_end == date_end
            ):
                raise ValueError("already exists")
        self._entries.append(NotInterested(profile_id, park_id, date_start, date_end))

    def remove(self, profile_id: int, park_id: int, date_start: date, date_end: date) -> None:
        self._entries = [
            e
            for e in self._entries
            if not (
                e.profile_id == profile_id
                and e.park_id == park_id
                and e.date_start == date_start
                and e.date_end == date_end
            )
        ]

    def list_for(self, profile_id: int) -> list[NotInterested]:
        return [e for e in self._entries if e.profile_id == profile_id]

    def load_skip_set(self, profile_id: int) -> set[tuple[int, date, date]]:
        return {(e.park_id, e.date_start, e.date_end) for e in self._entries if e.profile_id == profile_id}

    def record_sent(self, message_id: int, profile_id: int, park_id: int, date_start: date, date_end: date) -> None:
        pass

    def lookup_sent(self, message_id: int) -> tuple[int, int, date, date] | None:
        return None


class FakeProfileRepo:
    """Minimal ProfileRepo for not-interested tests. Only implements get_by_name."""

    def __init__(self) -> None:
        self._profiles: dict[str, Profile] = {}
        self._next_id = 1

    def create(self, profile: Profile) -> Profile:
        p = profile.model_copy(deep=True)
        p.id = self._next_id
        self._next_id += 1
        self._profiles[p.name] = p
        return p

    def get_by_name(self, name: str) -> Profile | None:
        return self._profiles.get(name)

    # Stub remaining ProfileRepo methods so the fake satisfies the protocol.
    def list_all(self) -> list[Profile]:
        return list(self._profiles.values())

    def list_enabled(self) -> list[Profile]:
        return [p for p in self._profiles.values() if p.enabled]

    def get_by_id(self, profile_id: int) -> Profile | None:
        for p in self._profiles.values():
            if p.id == profile_id:
                return p
        return None

    def update(self, profile: Profile) -> Profile:
        if profile.name in self._profiles:
            self._profiles[profile.name] = profile
        return profile

    def delete(self, name: str) -> bool:
        return False

    def set_enabled(self, name: str, enabled: bool) -> bool:
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
    """Minimal BCParksApi for not-interested tests."""

    def __init__(self, parks: list[Park] | None = None) -> None:
        self._parks = parks or []

    def list_parks(self, *, refresh: bool = False) -> list[Park]:
        return self._parks

    def list_maps(self, park_id: int) -> list:
        return []

    def map_availability(self, *, park_id: int, map_id: int, start: date, end: date, party_size: int = 1) -> dict:
        return {}

    def resource_details(self, *, park_id: int, map_id: int) -> dict:
        return {}


# Static assertion: the fakes satisfy the Protocols.
_ni_repo: NotInterestedRepo = FakeNotInterestedRepo()
_profile_repo: ProfileRepo = FakeProfileRepo()
_bcparks_api: BCParksApi = FakeBCParksApi()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


PARK_GOLDEN = Park(park_id=1, name="Golden Ears")
PARK_MURIN = Park(park_id=2, name="Murrin Park")


@pytest.fixture
def ni_repo() -> FakeNotInterestedRepo:
    return FakeNotInterestedRepo()


@pytest.fixture
def profile_repo() -> FakeProfileRepo:
    r = FakeProfileRepo()
    r.create(Profile(name="test-profile", enabled=True))
    r.create(Profile(name="other-profile", enabled=True))
    return r


@pytest.fixture
def api() -> FakeBCParksApi:
    return FakeBCParksApi(parks=[PARK_GOLDEN, PARK_MURIN])


# ---------------------------------------------------------------------------
# not_interested_add
# ---------------------------------------------------------------------------


class TestNotInterestedAdd:
    def test_add_success(self, ni_repo: FakeNotInterestedRepo, profile_repo: FakeProfileRepo, api: FakeBCParksApi) -> None:
        profile = profile_repo.get_by_name("test-profile")
        not_interested_add(ni_repo, profile_repo, api, "test-profile", "Golden Ears", date(2026, 8, 15), date(2026, 8, 17))
        entries = ni_repo.list_for(profile.id)
        assert len(entries) == 1
        assert entries[0].park_id == 1
        assert entries[0].date_start == date(2026, 8, 15)
        assert entries[0].date_end == date(2026, 8, 17)

    def test_add_missing_profile(self, ni_repo: FakeNotInterestedRepo, profile_repo: FakeProfileRepo, api: FakeBCParksApi) -> None:
        with pytest.raises(typer.Exit):
            not_interested_add(ni_repo, profile_repo, api, "ghost", "Golden Ears", date(2026, 8, 15), date(2026, 8, 17))

    def test_add_start_after_end(self, ni_repo: FakeNotInterestedRepo, profile_repo: FakeProfileRepo, api: FakeBCParksApi) -> None:
        with pytest.raises(typer.Exit):
            not_interested_add(ni_repo, profile_repo, api, "test-profile", "Golden Ears", date(2026, 8, 17), date(2026, 8, 15))

    def test_add_unknown_park(self, ni_repo: FakeNotInterestedRepo, profile_repo: FakeProfileRepo, api: FakeBCParksApi) -> None:
        with pytest.raises(typer.Exit):
            not_interested_add(ni_repo, profile_repo, api, "test-profile", "Nonexistent Park", date(2026, 8, 15), date(2026, 8, 17))

    def test_add_duplicate(self, ni_repo: FakeNotInterestedRepo, profile_repo: FakeProfileRepo, api: FakeBCParksApi) -> None:
        not_interested_add(ni_repo, profile_repo, api, "test-profile", "Golden Ears", date(2026, 8, 15), date(2026, 8, 17))
        with pytest.raises(typer.Exit):
            not_interested_add(ni_repo, profile_repo, api, "test-profile", "Golden Ears", date(2026, 8, 15), date(2026, 8, 17))

    def test_add_scoped_to_profile(self, ni_repo: FakeNotInterestedRepo, profile_repo: FakeProfileRepo, api: FakeBCParksApi) -> None:
        """Entry for one profile should not appear in another."""
        profile1 = profile_repo.get_by_name("test-profile")
        profile2 = profile_repo.get_by_name("other-profile")
        not_interested_add(ni_repo, profile_repo, api, "test-profile", "Golden Ears", date(2026, 8, 15), date(2026, 8, 17))
        assert len(ni_repo.list_for(profile1.id)) == 1
        assert len(ni_repo.list_for(profile2.id)) == 0


# ---------------------------------------------------------------------------
# not_interested_rm
# ---------------------------------------------------------------------------


class TestNotInterestedRm:
    def test_rm_existing(self, ni_repo: FakeNotInterestedRepo, profile_repo: FakeProfileRepo, api: FakeBCParksApi) -> None:
        profile = profile_repo.get_by_name("test-profile")
        not_interested_add(ni_repo, profile_repo, api, "test-profile", "Golden Ears", date(2026, 8, 15), date(2026, 8, 17))
        not_interested_rm(ni_repo, profile_repo, api, "test-profile", "Golden Ears", date(2026, 8, 15), date(2026, 8, 17))
        assert ni_repo.list_for(profile.id) == []

    def test_rm_missing_entry(self, ni_repo: FakeNotInterestedRepo, profile_repo: FakeProfileRepo, api: FakeBCParksApi) -> None:
        with pytest.raises(typer.Exit):
            not_interested_rm(ni_repo, profile_repo, api, "test-profile", "Golden Ears", date(2026, 8, 15), date(2026, 8, 17))

    def test_rm_missing_profile(self, ni_repo: FakeNotInterestedRepo, profile_repo: FakeProfileRepo, api: FakeBCParksApi) -> None:
        with pytest.raises(typer.Exit):
            not_interested_rm(ni_repo, profile_repo, api, "ghost", "Golden Ears", date(2026, 8, 15), date(2026, 8, 17))

    def test_rm_start_after_end(self, ni_repo: FakeNotInterestedRepo, profile_repo: FakeProfileRepo, api: FakeBCParksApi) -> None:
        with pytest.raises(typer.Exit):
            not_interested_rm(ni_repo, profile_repo, api, "test-profile", "Golden Ears", date(2026, 8, 17), date(2026, 8, 15))

    def test_rm_unknown_park(self, ni_repo: FakeNotInterestedRepo, profile_repo: FakeProfileRepo, api: FakeBCParksApi) -> None:
        with pytest.raises(typer.Exit):
            not_interested_rm(ni_repo, profile_repo, api, "test-profile", "Nonexistent Park", date(2026, 8, 15), date(2026, 8, 17))


# ---------------------------------------------------------------------------
# not_interested_list
# ---------------------------------------------------------------------------


class TestNotInterestedList:
    def test_list_entries(self, ni_repo: FakeNotInterestedRepo, profile_repo: FakeProfileRepo, api: FakeBCParksApi) -> None:
        not_interested_add(ni_repo, profile_repo, api, "test-profile", "Golden Ears", date(2026, 8, 15), date(2026, 8, 17))
        not_interested_add(ni_repo, profile_repo, api, "test-profile", "Murrin Park", date(2026, 9, 1), date(2026, 9, 3))
        not_interested_list(ni_repo, profile_repo, api, "test-profile")
        # No exception — renders table

    def test_list_empty(self, ni_repo: FakeNotInterestedRepo, profile_repo: FakeProfileRepo, api: FakeBCParksApi) -> None:
        not_interested_list(ni_repo, profile_repo, api, "test-profile")
        # No exception — shows "no entries" message

    def test_list_missing_profile(self, ni_repo: FakeNotInterestedRepo, profile_repo: FakeProfileRepo, api: FakeBCParksApi) -> None:
        with pytest.raises(typer.Exit):
            not_interested_list(ni_repo, profile_repo, api, "ghost")
