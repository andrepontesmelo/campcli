"""Unit tests for profile use-case functions (application/profile.py) with duck-typed fakes."""
from __future__ import annotations

from datetime import date, datetime

import pytest
import typer

from campcli.application.profile import (
    profile_delete,
    profile_disable,
    profile_enable,
    profile_list,
    profile_search,
    profile_show,
    profile_tg_add,
    profile_tg_list,
    profile_tg_rm,
    resolve_profile,
)
from campcli.domain.models import DriveTimes, ParkQuery, PatternSpec, Profile
from campcli.domain.ports import BCParksApi, ProfileRepo


# ---------------------------------------------------------------------------
# Duck-typed fake ProfileRepo
# ---------------------------------------------------------------------------


class FakeProfileRepo:
    """In-memory ProfileRepo for testing. Satisfies the ProfileRepo Protocol."""

    def __init__(self) -> None:
        self._profiles: dict[str, Profile] = {}
        self._patterns: dict[str, list[tuple[str, int]]] = {}
        self._parks: dict[str, list[tuple[str, str | None]]] = {}
        self._tg_ids: dict[str, list[int]] = {}
        self._next_id = 1

    def create(self, profile: Profile) -> Profile:
        p = profile.model_copy(deep=True)
        p.id = self._next_id
        self._next_id += 1
        ts = datetime.now().isoformat()
        p.created_at = ts
        p.updated_at = ts
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
        if profile.name in self._profiles:
            profile.updated_at = datetime.now().isoformat()
            self._profiles[profile.name] = profile
        return profile

    def delete(self, name: str) -> bool:
        if name in self._profiles:
            del self._profiles[name]
            self._patterns.pop(name, None)
            self._parks.pop(name, None)
            self._tg_ids.pop(name, None)
            return True
        return False

    def set_enabled(self, name: str, enabled: bool) -> bool:
        if name in self._profiles:
            self._profiles[name].enabled = enabled
            return True
        return False

    def add_pattern(self, profile_name: str, pattern: str, sort_order: int = 0) -> None:
        if profile_name not in self._profiles:
            raise KeyError(profile_name)
        self._patterns.setdefault(profile_name, []).append((pattern, sort_order))

    def remove_pattern(self, profile_name: str, pattern: str) -> bool:
        if profile_name not in self._patterns:
            return False
        before = len(self._patterns[profile_name])
        self._patterns[profile_name] = [
            (p, s) for p, s in self._patterns[profile_name] if p != pattern
        ]
        return len(self._patterns[profile_name]) < before

    def list_patterns(self, profile_name: str) -> list[PatternSpec]:
        if profile_name not in self._profiles:
            raise KeyError(profile_name)
        from campcli.domain.models import parse_pattern

        return [
            parse_pattern(p)
            for p, s in sorted(self._patterns.get(profile_name, []), key=lambda x: x[1])
        ]

    def add_park(self, profile_name: str, park_query: str, map_query: str | None = None) -> None:
        if profile_name not in self._profiles:
            raise KeyError(profile_name)
        self._parks.setdefault(profile_name, []).append((park_query, map_query))

    def remove_park(self, profile_name: str, park_query: str) -> bool:
        if profile_name not in self._parks:
            return False
        before = len(self._parks[profile_name])
        self._parks[profile_name] = [(p, m) for p, m in self._parks[profile_name] if p != park_query]
        return len(self._parks[profile_name]) < before

    def list_parks(self, profile_name: str) -> list[ParkQuery]:
        if profile_name not in self._profiles:
            raise KeyError(profile_name)
        return [ParkQuery(p, m) for p, m in self._parks.get(profile_name, [])]

    def add_tg_id(self, profile_name: str, tg_id: int) -> None:
        if profile_name not in self._profiles:
            raise KeyError(profile_name)
        tg_set = self._tg_ids.setdefault(profile_name, [])
        if tg_id not in tg_set:
            tg_set.append(tg_id)

    def remove_tg_id(self, profile_name: str, tg_id: int) -> bool:
        if profile_name not in self._tg_ids:
            return False
        before = len(self._tg_ids[profile_name])
        self._tg_ids[profile_name] = [t for t in self._tg_ids[profile_name] if t != tg_id]
        return len(self._tg_ids[profile_name]) < before

    def list_tg_ids(self, profile_name: str) -> list[int]:
        if profile_name not in self._profiles:
            raise KeyError(profile_name)
        return list(self._tg_ids.get(profile_name, []))


class _FakeBCParksApi:
    """Minimal fake BCParksApi returning empty results for search tests."""

    def list_parks(self, *, refresh: bool = False) -> list:
        return []

    def list_maps(self, park_id: int) -> list:
        return []

    def map_availability(
        self, *, park_id: int, map_id: int, start: date, end: date, party_size: int = 1
    ) -> dict:
        return {}

    def resource_details(self, *, park_id: int, map_id: int) -> dict:
        return {}


# Static assertion: the fakes satisfy the Protocols.
_profile_repo: ProfileRepo = FakeProfileRepo()
_bcparks_api: BCParksApi = _FakeBCParksApi()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def repo() -> FakeProfileRepo:
    r = FakeProfileRepo()
    r.create(Profile(name="alpha", max_horizon_months=6, max_drive_hours=2.0, rest_days_between_bookings=7))
    r.create(Profile(name="beta", max_horizon_months=3, max_drive_hours=3.0, rest_days_between_bookings=14))
    return r


@pytest.fixture
def repo_single_enabled() -> FakeProfileRepo:
    r = FakeProfileRepo()
    r.create(Profile(name="solo"))
    return r


@pytest.fixture
def repo_multi_enabled() -> FakeProfileRepo:
    r = FakeProfileRepo()
    r.create(Profile(name="one"))
    r.create(Profile(name="two"))
    return r


@pytest.fixture
def repo_all_disabled() -> FakeProfileRepo:
    r = FakeProfileRepo()
    r.create(Profile(name="offline", enabled=False))
    return r


# ---------------------------------------------------------------------------
# resolve_profile
# ---------------------------------------------------------------------------


class TestResolveProfile:
    def test_requested_name_found_enabled(self, repo: FakeProfileRepo) -> None:
        result = resolve_profile(repo, "alpha")
        assert result.name == "alpha"
        assert result.max_horizon_months == 6

    def test_requested_name_found_disabled(self, repo: FakeProfileRepo) -> None:
        repo.set_enabled("alpha", False)
        with pytest.raises(typer.Exit):
            resolve_profile(repo, "alpha")

    def test_requested_name_not_found(self, repo: FakeProfileRepo) -> None:
        with pytest.raises(typer.Exit):
            resolve_profile(repo, "nonexistent")

    def test_no_requested_single_enabled(self, repo_single_enabled: FakeProfileRepo) -> None:
        result = resolve_profile(repo_single_enabled, None)
        assert result.name == "solo"

    def test_no_requested_no_enabled(self, repo_all_disabled: FakeProfileRepo) -> None:
        with pytest.raises(typer.Exit):
            resolve_profile(repo_all_disabled, None)

    def test_no_requested_multi_enabled(self, repo_multi_enabled: FakeProfileRepo) -> None:
        with pytest.raises(typer.Exit):
            resolve_profile(repo_multi_enabled, None)


# ---------------------------------------------------------------------------
# profile_list
# ---------------------------------------------------------------------------


class TestProfileList:
    def test_list_empty(self) -> None:
        r = FakeProfileRepo()
        profile_list(r)
        # No exception means success

    def test_list_with_profiles(self, repo: FakeProfileRepo) -> None:
        profile_list(repo)
        # No exception — renders header + rows

    def test_list_includes_disabled(self, repo: FakeProfileRepo) -> None:
        repo.set_enabled("alpha", False)
        profile_list(repo)
        # Disabled profiles still appear in list


# ---------------------------------------------------------------------------
# profile_show
# ---------------------------------------------------------------------------


class TestProfileShow:
    def test_show_existing(self, repo: FakeProfileRepo) -> None:
        profile_show(repo, "alpha")
        # No exception — renders details

    def test_show_missing(self, repo: FakeProfileRepo) -> None:
        with pytest.raises(typer.Exit):
            profile_show(repo, "ghost")


# ---------------------------------------------------------------------------
# profile_delete
# ---------------------------------------------------------------------------


class TestProfileDelete:
    def test_delete_existing(self, repo: FakeProfileRepo) -> None:
        profile_delete(repo, "alpha")
        assert repo.get_by_name("alpha") is None

    def test_delete_missing(self, repo: FakeProfileRepo) -> None:
        with pytest.raises(typer.Exit):
            profile_delete(repo, "ghost")


# ---------------------------------------------------------------------------
# profile_enable / profile_disable
# ---------------------------------------------------------------------------


class TestProfileEnableDisable:
    def test_disable_existing(self, repo: FakeProfileRepo) -> None:
        profile_disable(repo, "alpha")
        assert repo.get_by_name("alpha").enabled is False

    def test_disable_missing(self, repo: FakeProfileRepo) -> None:
        with pytest.raises(typer.Exit):
            profile_disable(repo, "ghost")

    def test_enable_existing(self, repo: FakeProfileRepo) -> None:
        repo.set_enabled("alpha", False)
        profile_enable(repo, "alpha")
        assert repo.get_by_name("alpha").enabled is True

    def test_enable_missing(self, repo: FakeProfileRepo) -> None:
        with pytest.raises(typer.Exit):
            profile_enable(repo, "ghost")


# ---------------------------------------------------------------------------
# profile_tg_add / profile_tg_rm / profile_tg_list
# ---------------------------------------------------------------------------


class TestProfileTgCommands:
    def test_tg_add(self, repo: FakeProfileRepo) -> None:
        profile_tg_add(repo, "alpha", 12345)
        assert repo.list_tg_ids("alpha") == [12345]

    def test_tg_add_accumulates(self, repo: FakeProfileRepo) -> None:
        profile_tg_add(repo, "alpha", 12345)
        profile_tg_add(repo, "alpha", 67890)
        assert repo.list_tg_ids("alpha") == [12345, 67890]

    def test_tg_add_missing_profile(self, repo: FakeProfileRepo) -> None:
        with pytest.raises(typer.Exit):
            profile_tg_add(repo, "ghost", 12345)

    def test_tg_rm_existing(self, repo: FakeProfileRepo) -> None:
        profile_tg_add(repo, "alpha", 12345)
        profile_tg_rm(repo, "alpha", 12345)
        assert repo.list_tg_ids("alpha") == []

    def test_tg_rm_not_found(self, repo: FakeProfileRepo) -> None:
        with pytest.raises(typer.Exit):
            profile_tg_rm(repo, "alpha", 99999)

    def test_tg_rm_missing_profile(self, repo: FakeProfileRepo) -> None:
        with pytest.raises(typer.Exit):
            profile_tg_rm(repo, "ghost", 12345)

    def test_tg_list(self, repo: FakeProfileRepo) -> None:
        profile_tg_add(repo, "alpha", 12345)
        profile_tg_add(repo, "alpha", 67890)
        profile_tg_list(repo, "alpha")
        # No exception

    def test_tg_list_empty(self, repo: FakeProfileRepo) -> None:
        profile_tg_list(repo, "alpha")
        # No exception — shows "no Telegram IDs" message

    def test_tg_list_missing_profile(self, repo: FakeProfileRepo) -> None:
        with pytest.raises(typer.Exit):
            profile_tg_list(repo, "ghost")


# ---------------------------------------------------------------------------
# profile_search (validation only — no API)
# ---------------------------------------------------------------------------


class TestProfileSearch:
    def test_search_disabled_profile(self, repo: FakeProfileRepo) -> None:
        repo.set_enabled("alpha", False)
        with pytest.raises(typer.Exit):
            profile_search(
                repo, None, DriveTimes.empty(), "alpha",
                group_by="weekend",
            )

    def test_search_missing_profile(self, repo: FakeProfileRepo) -> None:
        with pytest.raises(typer.Exit):
            profile_search(
                repo, None, DriveTimes.empty(), "ghost",
                group_by="weekend",
            )

    def test_search_invalid_group_by(self, repo: FakeProfileRepo) -> None:
        with pytest.raises(typer.Exit):
            profile_search(
                repo, None, DriveTimes.empty(), "alpha",
                group_by="invalid",
            )

    def test_search_enabled_profile_no_crash(self, repo: FakeProfileRepo) -> None:
        """Valid params raise typer.Exit(3) because fake API returns no matches."""
        api = _FakeBCParksApi()
        with pytest.raises(typer.Exit):
            profile_search(
                repo, api, DriveTimes.empty(), "alpha",
                group_by="weekend",
            )
