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
