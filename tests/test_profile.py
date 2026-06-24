"""Tests for Profile model, pattern parser, and loader."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from campcli.application.profile import (
    AllowedEntry,
    Profile,
    load_profile,
    parse_pattern,
)
from campcli.domain.models import Map, Park


# ---------------------------------------------------------------------------
# parse_pattern
# ---------------------------------------------------------------------------

class TestParsePattern:
    def test_fri_sun(self):
        assert parse_pattern("fri-sun") == (4, 2)

    def test_sat_sun(self):
        assert parse_pattern("sat-sun") == (5, 1)

    def test_mon_fri(self):
        assert parse_pattern("mon-fri") == (0, 4)

    def test_case_insensitive(self):
        assert parse_pattern("FRI-sun") == (4, 2)
        assert parse_pattern("SAT-SUN") == (5, 1)

    def test_same_day_rejected(self):
        with pytest.raises(ValueError, match="no wrap-around or same-day"):
            parse_pattern("fri-fri")

    def test_invalid_no_hyphen(self):
        with pytest.raises(ValueError, match="expected 'day-day' format"):
            parse_pattern("fri")

    def test_invalid_start_day(self):
        with pytest.raises(ValueError, match="unknown day"):
            parse_pattern("xyz-sun")

    def test_invalid_end_day(self):
        with pytest.raises(ValueError, match="unknown day"):
            parse_pattern("fri-xyz")

    def test_wrap_around_rejected(self):
        with pytest.raises(ValueError, match="no wrap-around"):
            parse_pattern("sun-fri")


# ---------------------------------------------------------------------------
# Profile model
# ---------------------------------------------------------------------------

class TestProfileDefault:
    def test_default_patterns(self):
        p = Profile()
        assert p.patterns == ["fri-sun"]

    def test_default_field_values(self):
        p = Profile()
        assert p.max_horizon_months == 3
        assert p.max_drive_hours == 3.0
        assert p.min_start_date is None
        assert p.rest_days_between_bookings == 14
        assert p.allowed == []

    def test_tg_allowed_ids_default_empty(self):
        p = Profile()
        assert p.tg_allowed_ids == []

    def test_tg_allowed_ids_custom(self):
        p = Profile(tg_allowed_ids=[12345, 67890])
        assert p.tg_allowed_ids == [12345, 67890]

    def test_allowed_park_ids_default_empty(self):
        p = Profile()
        assert p.allowed_park_ids == {}

    def test_pattern_tuples(self):
        p = Profile(patterns=["fri-sun", "sat-sun"])
        assert p.pattern_tuples() == [(4, 2), (5, 1)]

    def test_min_start_date_parsed_none(self):
        p = Profile()
        assert p.min_start_date_parsed() is None

    def test_min_start_date_parsed_value(self):
        p = Profile(min_start_date="2026-08-01")
        assert p.min_start_date_parsed() == date(2026, 8, 1)

    def test_extra_fields_rejected(self):
        with pytest.raises(ValueError):
            Profile.model_validate({"patterns": ["fri-sun"], "unknown": True})


class TestProfileFromJson:
    def test_valid_json(self):
        raw = json.dumps({
            "patterns": ["fri-sun"],
            "max_horizon_months": 2,
            "max_drive_hours": 4.0,
            "min_start_date": "2026-07-01",
            "rest_days_between_bookings": 7,
            "tg_allowed_ids": [12345],
            "allowed": [{"park": "Golden Ears"}],
        })
        p = Profile.model_validate_json(raw)
        assert p.patterns == ["fri-sun"]
        assert p.max_horizon_months == 2
        assert p.max_drive_hours == 4.0
        assert p.min_start_date == "2026-07-01"
        assert p.rest_days_between_bookings == 7
        assert p.tg_allowed_ids == [12345]
        assert len(p.allowed) == 1
        assert p.allowed[0].park == "Golden Ears"
        assert p.allowed[0].map is None

    def test_json_without_tg_allowed_ids_uses_default(self):
        raw = json.dumps({"patterns": ["fri-sun"]})
        p = Profile.model_validate_json(raw)
        assert p.tg_allowed_ids == []

    def test_default_json_contains_tg_allowed_ids(self, tmp_path):
        from unittest.mock import patch
        from campcli.application.profile import _DEFAULT_JSON
        assert "tg_allowed_ids" in _DEFAULT_JSON
        assert _DEFAULT_JSON["tg_allowed_ids"] == []


# ---------------------------------------------------------------------------
# load_profile
# ---------------------------------------------------------------------------

class FakeApi:
    """Minimal BCParksApi for testing load_profile."""

    def __init__(self, parks: list[Park] | None = None) -> None:
        self._parks = parks or [
            Park(park_id=1, name="Cultus Lake", region="test"),
            Park(park_id=2, name="Golden Ears", region="test"),
        ]

    def list_parks(self, *, refresh: bool = False) -> list[Park]:
        return self._parks

    def list_maps(self, park_id: int) -> list[Map]:
        return [
            Map(map_id=10, park_id=1, name="Maple Bay"),
            Map(map_id=11, park_id=1, name="Main"),
            Map(map_id=20, park_id=2, name="Alouette"),
            Map(map_id=21, park_id=2, name="Gold Creek"),
        ]


class TestLoadProfile:
    def test_file_missing_generates_default(self, tmp_path: Path) -> None:
        """Scenario: File missing → generates default profile.json."""
        from campcli.constants import CONFIG_DIR, PROFILE_PATH

        # Override file paths for the test scope.
        old_cfg = CONFIG_DIR
        old_pr = PROFILE_PATH

        # We need to patch CONFIG_DIR so PROFILE_PATH uses tmp_path.
        import campcli.constants as const_mod
        import campcli.application.profile as profile_mod

        test_dir = tmp_path / ".campcli"
        # Temporarily patch the constant used by profile.py
        from unittest.mock import patch

        with patch.object(profile_mod, "PROFILE_PATH", test_dir / "profile.json"):
            with patch.object(const_mod, "CONFIG_DIR", test_dir):
                profile = load_profile(FakeApi())
                assert profile.patterns == ["fri-sun"]
                assert profile.max_horizon_months == 3
                assert profile.allowed == []
                assert (test_dir / "profile.json").exists()

    def test_invalid_json_raises(self, tmp_path: Path) -> None:
        from unittest.mock import patch

        test_path = tmp_path / "profile.json"
        test_path.write_text("not json")
        with patch("campcli.application.profile.PROFILE_PATH", test_path):
            with pytest.raises(ValueError):
                load_profile(FakeApi())

    def test_bad_schema_rejected(self, tmp_path: Path) -> None:
        from unittest.mock import patch

        test_path = tmp_path / "profile.json"
        test_path.write_text(json.dumps({"patterns": "not-a-list"}))
        with patch("campcli.application.profile.PROFILE_PATH", test_path):
            with pytest.raises(ValueError):
                load_profile(FakeApi())

    def test_bad_pattern_rejected(self, tmp_path: Path) -> None:
        from unittest.mock import patch

        test_path = tmp_path / "profile.json"
        test_path.write_text(json.dumps({"patterns": ["fri-sun", "xyz"]}))
        with patch("campcli.application.profile.PROFILE_PATH", test_path):
            with pytest.raises(ValueError, match="invalid pattern"):
                load_profile(FakeApi())

    def test_unknown_park_name(self, tmp_path: Path) -> None:
        from unittest.mock import patch

        test_path = tmp_path / "profile.json"
        test_path.write_text(json.dumps({
            "allowed": [{"park": "Nonexistent Park"}],
        }))
        with patch("campcli.application.profile.PROFILE_PATH", test_path):
            with pytest.raises(ValueError, match="unknown park"):
                load_profile(FakeApi())

    def test_unknown_map_name(self, tmp_path: Path) -> None:
        from unittest.mock import patch

        test_path = tmp_path / "profile.json"
        test_path.write_text(json.dumps({
            "allowed": [{"park": "Cultus Lake", "map": "Fake Beach"}],
        }))
        with patch("campcli.application.profile.PROFILE_PATH", test_path):
            with pytest.raises(ValueError, match="unknown map"):
                load_profile(FakeApi())

    def test_allowed_resolves_park_only(self, tmp_path: Path) -> None:
        from unittest.mock import patch

        test_path = tmp_path / "profile.json"
        test_path.write_text(json.dumps({
            "allowed": [{"park": "Cultus Lake"}],
        }))
        with patch("campcli.application.profile.PROFILE_PATH", test_path):
            profile = load_profile(FakeApi())
            assert profile.allowed_park_ids == {1: None}  # all maps

    def test_allowed_resolves_park_and_map(self, tmp_path: Path) -> None:
        from unittest.mock import patch

        test_path = tmp_path / "profile.json"
        test_path.write_text(json.dumps({
            "allowed": [{"park": "Cultus Lake", "map": "Maple Bay"}],
        }))
        with patch("campcli.application.profile.PROFILE_PATH", test_path):
            profile = load_profile(FakeApi())
            assert profile.allowed_park_ids == {1: {10}}

    def test_empty_allowed_skips_resolution(self, tmp_path: Path) -> None:
        from unittest.mock import patch

        test_path = tmp_path / "profile.json"
        test_path.write_text(json.dumps({"allowed": []}))
        with patch("campcli.application.profile.PROFILE_PATH", test_path):
            profile = load_profile(FakeApi())
            assert profile.allowed_park_ids == {}
