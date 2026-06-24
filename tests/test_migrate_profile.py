"""Tests for migrate_profile_json_to_db()."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from campcli.application.migrate_profile import migrate_profile_json_to_db
from campcli.domain.models import Profile


class TestMigrateProfileJsonToDb:
    def test_json_exists_db_empty_migrates(self, tmp_path: Path, profile_repo) -> None:
        """profile.json exists, DB empty → migration occurs, profile created, JSON deleted."""
        json_path = tmp_path / "profile.json"
        json_path.write_text(json.dumps({
            "patterns": ["fri-sun"],
            "max_horizon_months": 2,
            "max_drive_hours": 4.0,
            "min_start_date": "2026-07-01",
            "rest_days_between_bookings": 7,
            "tg_allowed_ids": [12345],
            "allowed": [{"park": "Bowron Lake"}],
        }))

        result = migrate_profile_json_to_db(json_path, profile_repo)
        assert result is True

        # Profile 'default' should exist in DB.
        default = profile_repo.get_by_name("default")
        assert default is not None
        assert default.max_horizon_months == 2
        assert default.max_drive_hours == 4.0
        assert default.min_start_date == "2026-07-01"
        assert default.rest_days_between_bookings == 7
        assert default.enabled is True
        assert default.tg_allowed_ids == [12345]
        assert len(default.patterns) > 0
        assert any(pq.park_query == "Bowron Lake" for pq in default.parks)

        # JSON file should be deleted.
        assert not json_path.exists()

    def test_json_exists_db_has_profiles_skips(self, tmp_path: Path, profile_repo) -> None:
        """profile.json exists but DB has profiles → no migration, JSON untouched."""
        # Pre-create a profile.
        profile_repo.create(Profile(name="existing"))

        json_path = tmp_path / "profile.json"
        json_path.write_text(json.dumps({"patterns": ["fri-sun"]}))

        result = migrate_profile_json_to_db(json_path, profile_repo)
        assert result is False

        # JSON still exists.
        assert json_path.exists()
        # 'default' not created.
        assert profile_repo.get_by_name("default") is None

    def test_json_missing_noop(self, tmp_path: Path, profile_repo) -> None:
        """No profile.json → no-op."""
        json_path = tmp_path / "profile.json"
        assert not json_path.exists()

        result = migrate_profile_json_to_db(json_path, profile_repo)
        assert result is False

    def test_json_malformed_raises(self, tmp_path: Path, profile_repo) -> None:
        """Malformed JSON raises ValueError."""
        json_path = tmp_path / "profile.json"
        json_path.write_text("not json")

        with pytest.raises(ValueError, match="not valid JSON"):
            migrate_profile_json_to_db(json_path, profile_repo)

    def test_json_minimal_defaults(self, tmp_path: Path, profile_repo) -> None:
        """Minimal JSON uses defaults for missing fields."""
        json_path = tmp_path / "profile.json"
        json_path.write_text(json.dumps({}))

        result = migrate_profile_json_to_db(json_path, profile_repo)
        assert result is True

        default = profile_repo.get_by_name("default")
        assert default is not None
        assert default.max_horizon_months == 3
        assert default.max_drive_hours == 3.0
        assert default.min_start_date is None
        assert default.rest_days_between_bookings == 14
        assert default.tg_allowed_ids == []
        assert not json_path.exists()

    def test_migrate_with_map_query(self, tmp_path: Path, profile_repo) -> None:
        """Profile with specific map query is migrated correctly."""
        json_path = tmp_path / "profile.json"
        json_path.write_text(json.dumps({
            "allowed": [{"park": "Bowron Lake", "map": "Main"}],
        }))

        result = migrate_profile_json_to_db(json_path, profile_repo)
        assert result is True

        default = profile_repo.get_by_name("default")
        assert default is not None
        assert len(default.parks) == 1
        assert default.parks[0].park_query == "Bowron Lake"
        assert default.parks[0].map_query == "Main"
