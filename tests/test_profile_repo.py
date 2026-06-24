"""Unit tests for ProfileRepo using in-memory SQLite."""
from __future__ import annotations

import sqlite3

from campcli.domain.models import Profile
from campcli.infrastructure.store import SqliteStore


class TestProfileRepo:
    def test_create_and_get_by_name(self, profile_repo: SqliteStore):
        p = profile_repo.create(Profile(name="test"))
        assert p.id is not None
        assert p.name == "test"
        assert p.enabled is True
        assert p.created_at == "2026-01-01T12:00:00"
        assert p.updated_at == "2026-01-01T12:00:00"

        loaded = profile_repo.get_by_name("test")
        assert loaded is not None
        assert loaded.name == "test"
        assert loaded.id == p.id

    def test_get_by_name_missing(self, profile_repo: SqliteStore):
        assert profile_repo.get_by_name("nope") is None

    def test_create_with_all_fields(self, profile_repo: SqliteStore):
        p = Profile(
            name="golden",
            max_horizon_months=6,
            max_drive_hours=4.5,
            min_start_date="2026-07-01",
            rest_days_between_bookings=7,
            enabled=False,
        )
        created = profile_repo.create(p)
        assert created.max_horizon_months == 6
        assert created.max_drive_hours == 4.5
        assert created.min_start_date == "2026-07-01"
        assert created.rest_days_between_bookings == 7
        assert created.enabled is False

        loaded = profile_repo.get_by_name("golden")
        assert loaded is not None
        assert loaded.max_horizon_months == 6

    def test_create_uses_clock_for_timestamps(self, profile_repo: SqliteStore, clock):
        p = profile_repo.create(Profile(name="ts-test"))
        assert p.created_at == "2026-01-01T12:00:00"
        assert p.updated_at == "2026-01-01T12:00:00"

    def test_list_all_empty(self, profile_repo: SqliteStore):
        assert profile_repo.list_all() == []

    def test_list_all(self, profile_repo: SqliteStore):
        profile_repo.create(Profile(name="a"))
        profile_repo.create(Profile(name="b"))
        profile_repo.create(Profile(name="c"))
        names = [p.name for p in profile_repo.list_all()]
        assert names == ["a", "b", "c"]

    def test_list_enabled_only(self, profile_repo: SqliteStore):
        profile_repo.create(Profile(name="enabled1"))
        profile_repo.create(Profile(name="enabled2"))
        profile_repo.create(Profile(name="disabled", enabled=False))
        enabled = profile_repo.list_enabled()
        assert [p.name for p in enabled] == ["enabled1", "enabled2"]

    def test_list_enabled_empty(self, profile_repo: SqliteStore):
        assert profile_repo.list_enabled() == []

    def test_update(self, profile_repo: SqliteStore, clock):
        created = profile_repo.create(Profile(name="update-me", max_horizon_months=3))

        created.max_horizon_months = 6
        created.max_drive_hours = 2.0
        created.min_start_date = "2026-08-01"
        created.rest_days_between_bookings = 3
        created.enabled = False

        updated = profile_repo.update(created)
        assert updated.max_horizon_months == 6
        assert updated.max_drive_hours == 2.0
        assert updated.min_start_date == "2026-08-01"
        assert updated.rest_days_between_bookings == 3
        assert updated.enabled is False
        assert updated.created_at == "2026-01-01T12:00:00"
        assert updated.updated_at == "2026-01-01T12:00:00"

        loaded = profile_repo.get_by_name("update-me")
        assert loaded is not None
        assert loaded.max_horizon_months == 6
        assert loaded.rest_days_between_bookings == 3

    def test_delete_returns_true(self, profile_repo: SqliteStore):
        profile_repo.create(Profile(name="delete-me"))
        assert profile_repo.delete("delete-me") is True
        assert profile_repo.get_by_name("delete-me") is None

    def test_delete_returns_false(self, profile_repo: SqliteStore):
        assert profile_repo.delete("never-existed") is False

    def test_set_enabled_true(self, profile_repo: SqliteStore):
        profile_repo.create(Profile(name="toggle", enabled=False))
        result = profile_repo.set_enabled("toggle", True)
        assert result is True
        loaded = profile_repo.get_by_name("toggle")
        assert loaded is not None
        assert loaded.enabled is True

    def test_set_enabled_false(self, profile_repo: SqliteStore):
        profile_repo.create(Profile(name="toggle-off"))
        result = profile_repo.set_enabled("toggle-off", False)
        assert result is True
        loaded = profile_repo.get_by_name("toggle-off")
        assert loaded is not None
        assert loaded.enabled is False

    def test_set_enabled_missing(self, profile_repo: SqliteStore):
        assert profile_repo.set_enabled("ghost", True) is False

    def test_unique_name_raises(self, profile_repo: SqliteStore):
        profile_repo.create(Profile(name="unique"))
        import pytest
        with pytest.raises(sqlite3.IntegrityError):
            profile_repo.create(Profile(name="unique"))

    def test_empty_child_lists(self, profile_repo: SqliteStore):
        p = profile_repo.create(Profile(name="empty-child"))
        assert p.patterns == []
        assert p.parks == []
        assert p.tg_allowed_ids == []


class TestChildCRUD:
    """Child table CRUD (patterns, parks, telegram IDs)."""

    def _create(self, profile_repo: SqliteStore, name: str = "test") -> Profile:
        return profile_repo.create(Profile(name=name))

    # ---- patterns ----------------------------------------------------------

    def test_add_and_list_patterns(self, profile_repo: SqliteStore):
        self._create(profile_repo)
        profile_repo.add_pattern("test", "fri-sun", sort_order=0)
        profile_repo.add_pattern("test", "sat-sun:1-1", sort_order=1)
        pats = profile_repo.list_patterns("test")
        assert len(pats) == 2
        assert pats[0].weekday == 4  # fri
        assert pats[0].span_nights == 2
        assert pats[1].weekday == 5  # sat
        assert pats[1].span_nights == 1  # sat-sun = 1 night
        assert pats[1].min_nights == 1
        assert pats[1].max_nights == 1

    def test_list_patterns_empty(self, profile_repo: SqliteStore):
        self._create(profile_repo)
        assert profile_repo.list_patterns("test") == []

    def test_list_patterns_missing_profile(self, profile_repo: SqliteStore):
        assert profile_repo.list_patterns("nope") == []

    def test_remove_pattern(self, profile_repo: SqliteStore):
        self._create(profile_repo)
        profile_repo.add_pattern("test", "fri-sun")
        assert profile_repo.remove_pattern("test", "fri-sun") is True
        assert profile_repo.list_patterns("test") == []

    def test_remove_pattern_not_found(self, profile_repo: SqliteStore):
        self._create(profile_repo)
        assert profile_repo.remove_pattern("test", "nope") is False

    def test_remove_pattern_missing_profile(self, profile_repo: SqliteStore):
        assert profile_repo.remove_pattern("nope", "fri-sun") is False

    def test_add_pattern_raises_on_missing_profile(self, profile_repo: SqliteStore):
        import pytest
        with pytest.raises(KeyError, match="not found"):
            profile_repo.add_pattern("nope", "fri-sun")

    # ---- parks -------------------------------------------------------------

    def test_add_and_list_parks(self, profile_repo: SqliteStore):
        self._create(profile_repo)
        profile_repo.add_park("test", "Bowron Lake")
        profile_repo.add_park("test", "Golden Ears", map_query="Main")
        parks = profile_repo.list_parks("test")
        assert len(parks) == 2
        assert parks[0].park_query == "Bowron Lake"
        assert parks[0].map_query is None
        assert parks[1].park_query == "Golden Ears"
        assert parks[1].map_query == "Main"

    def test_list_parks_empty(self, profile_repo: SqliteStore):
        self._create(profile_repo)
        assert profile_repo.list_parks("test") == []

    def test_list_parks_missing_profile(self, profile_repo: SqliteStore):
        assert profile_repo.list_parks("nope") == []

    def test_remove_park(self, profile_repo: SqliteStore):
        self._create(profile_repo)
        profile_repo.add_park("test", "Bowron Lake")
        assert profile_repo.remove_park("test", "Bowron Lake") is True
        assert profile_repo.list_parks("test") == []

    def test_remove_park_not_found(self, profile_repo: SqliteStore):
        self._create(profile_repo)
        assert profile_repo.remove_park("test", "nope") is False

    def test_remove_park_missing_profile(self, profile_repo: SqliteStore):
        assert profile_repo.remove_park("nope", "Bowron Lake") is False

    def test_add_park_raises_on_missing_profile(self, profile_repo: SqliteStore):
        import pytest
        with pytest.raises(KeyError, match="not found"):
            profile_repo.add_park("nope", "Bowron Lake")

    # ---- telegram IDs ------------------------------------------------------

    def test_add_and_list_tg_ids(self, profile_repo: SqliteStore):
        self._create(profile_repo)
        profile_repo.add_tg_id("test", 12345)
        profile_repo.add_tg_id("test", 67890)
        ids = profile_repo.list_tg_ids("test")
        assert ids == [12345, 67890]

    def test_list_tg_ids_empty(self, profile_repo: SqliteStore):
        self._create(profile_repo)
        assert profile_repo.list_tg_ids("test") == []

    def test_list_tg_ids_missing_profile(self, profile_repo: SqliteStore):
        assert profile_repo.list_tg_ids("nope") == []

    def test_remove_tg_id(self, profile_repo: SqliteStore):
        self._create(profile_repo)
        profile_repo.add_tg_id("test", 12345)
        assert profile_repo.remove_tg_id("test", 12345) is True
        assert profile_repo.list_tg_ids("test") == []

    def test_remove_tg_id_not_found(self, profile_repo: SqliteStore):
        self._create(profile_repo)
        assert profile_repo.remove_tg_id("test", 999) is False

    def test_remove_tg_id_missing_profile(self, profile_repo: SqliteStore):
        assert profile_repo.remove_tg_id("nope", 12345) is False

    def test_add_tg_id_raises_on_missing_profile(self, profile_repo: SqliteStore):
        import pytest
        with pytest.raises(KeyError, match="not found"):
            profile_repo.add_tg_id("nope", 12345)

    # ---- cascade on profile delete -----------------------------------------

    def test_delete_profile_cascades_to_patterns(self, profile_repo: SqliteStore):
        self._create(profile_repo)
        profile_repo.add_pattern("test", "fri-sun")
        profile_repo.add_park("test", "Bowron Lake")
        profile_repo.add_tg_id("test", 12345)
        profile_repo.delete("test")
        # Children should be gone.
        assert profile_repo.list_patterns("test") == []
        assert profile_repo.list_parks("test") == []
        assert profile_repo.list_tg_ids("test") == []

    # ---- children loaded on get_by_name ------------------------------------

    def test_get_by_name_loads_children(self, profile_repo: SqliteStore):
        self._create(profile_repo)
        profile_repo.add_pattern("test", "fri-sun")
        profile_repo.add_park("test", "Bowron Lake")
        profile_repo.add_tg_id("test", 12345)
        p = profile_repo.get_by_name("test")
        assert p is not None
        assert len(p.patterns) == 1
        assert p.patterns[0].weekday == 4
        assert len(p.parks) == 1
        assert p.parks[0].park_query == "Bowron Lake"
        assert p.tg_allowed_ids == [12345]

    def test_list_all_loads_children(self, profile_repo: SqliteStore):
        self._create(profile_repo, "a")
        self._create(profile_repo, "b")
        profile_repo.add_pattern("a", "fri-sun")
        profile_repo.add_park("b", "Golden Ears")
        profiles = profile_repo.list_all()
        by_name = {p.name: p for p in profiles}
        assert len(by_name["a"].patterns) == 1
        assert len(by_name["b"].parks) == 1

    def test_list_enabled_loads_children(self, profile_repo: SqliteStore):
        self._create(profile_repo, "enabled1")
        self._create(profile_repo, "disabled1")
        profile_repo.set_enabled("disabled1", False)
        profile_repo.add_pattern("enabled1", "fri-sun")
        profile_repo.add_pattern("disabled1", "sat-sun")
        enabled = profile_repo.list_enabled()
        names = {p.name for p in enabled}
        assert "enabled1" in names
        assert "disabled1" not in names
        for p in enabled:
            if p.name == "enabled1":
                assert len(p.patterns) == 1
