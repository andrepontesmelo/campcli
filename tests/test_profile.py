"""Tests for PatternSpec, parse_pattern, and the domain Profile model."""
from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from campcli.domain.models import (
    ParkQuery,
    PatternSpec,
    Profile,
    parse_pattern,
)


# ---------------------------------------------------------------------------
# parse_pattern
# ---------------------------------------------------------------------------

class TestParsePattern:
    def test_fri_sun(self):
        assert parse_pattern("fri-sun") == PatternSpec(4, 2, 2, 2)

    def test_sat_sun(self):
        assert parse_pattern("sat-sun") == PatternSpec(5, 1, 1, 1)

    def test_mon_fri(self):
        assert parse_pattern("mon-fri") == PatternSpec(0, 4, 4, 4)

    def test_case_insensitive(self):
        assert parse_pattern("FRI-sun") == PatternSpec(4, 2, 2, 2)
        assert parse_pattern("SAT-SUN") == PatternSpec(5, 1, 1, 1)

    def test_same_day_rejected(self):
        with pytest.raises(ValueError, match="same-day pattern"):
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

    def test_sun_fri(self):
        """sun-fri wraps: (end-start)%7 = (4-6)%7 = 5 nights (<=5, OK)."""
        assert parse_pattern("sun-fri") == PatternSpec(6, 5, 5, 5)

    # ---- min-max suffix tests ------------------------------------------------

    def test_fri_mon_2_3(self):
        result = parse_pattern("fri-mon:2-3")
        assert result == PatternSpec(4, 3, 2, 3)

    def test_fri_mon_2_2(self):
        result = parse_pattern("fri-mon:2-2")
        assert result == PatternSpec(4, 3, 2, 2)

    def test_bare_pattern_uses_span_for_min_max(self):
        result = parse_pattern("fri-sun")
        assert result == PatternSpec(4, 2, 2, 2)

    def test_min_less_than_one_rejected(self):
        with pytest.raises(ValueError, match="must be >= 1"):
            parse_pattern("fri-mon:0-3")

    def test_min_greater_than_max_rejected(self):
        with pytest.raises(ValueError, match="must be <= max"):
            parse_pattern("fri-mon:3-2")

    def test_max_greater_than_span_rejected(self):
        with pytest.raises(ValueError, match="exceeds span"):
            parse_pattern("fri-mon:2-5")

    def test_malformed_suffix_rejected(self):
        with pytest.raises(ValueError, match="malformed min-max suffix"):
            parse_pattern("fri-mon:abc")

    def test_single_sided_suffix_rejected(self):
        with pytest.raises(ValueError, match="malformed min-max suffix"):
            parse_pattern("fri-mon:2")

    def test_over_long_suffix_rejected(self):
        with pytest.raises(ValueError, match="malformed min-max suffix"):
            parse_pattern("fri-mon:2-3-4")

    # ---- wrap-around / span-limit tests ----------------------------------------

    def test_wrap_around_rejected(self):
        """sun-sat (6 nights) and mon-sun (6 nights) exceed the 5-night cap."""
        with pytest.raises(ValueError, match="span too long"):
            parse_pattern("sun-sat")
        with pytest.raises(ValueError, match="span too long"):
            parse_pattern("mon-sun")

    def test_max_nights_equals_span_boundary(self):
        """min=max=span (3) is valid: fri-mon:3-3."""
        assert parse_pattern("fri-mon:3-3") == PatternSpec(4, 3, 3, 3)

    def test_bare_pattern_fri_mon(self):
        """Bare fri-mon (wrap, 3 nights) succeeds — short forward wrap."""
        assert parse_pattern("fri-mon") == PatternSpec(4, 3, 3, 3)

    def test_max_span_boundary(self):
        """wed-mon = 5 nights — boundary of the max-span cap."""
        assert parse_pattern("wed-mon") == PatternSpec(2, 5, 5, 5)


# ---------------------------------------------------------------------------
# Profile model (domain)
# ---------------------------------------------------------------------------

class TestDomainProfile:
    def test_default_patterns_empty(self):
        p = Profile(name="test")
        assert p.patterns == []

    def test_default_field_values(self):
        p = Profile(name="test")
        assert p.max_horizon_months == 3
        assert p.max_drive_hours == 3.0
        assert p.min_start_date is None
        assert p.rest_days_between_bookings == 14

    def test_tg_allowed_ids_default_empty(self):
        p = Profile(name="test")
        assert p.tg_allowed_ids == []

    def test_tg_allowed_ids_custom(self):
        p = Profile(name="test", tg_allowed_ids=[12345, 67890])
        assert p.tg_allowed_ids == [12345, 67890]

    def test_patterns_as_parsed_specs(self):
        pat = parse_pattern("fri-sun")
        p = Profile(name="test", patterns=[pat])
        assert p.patterns == [PatternSpec(4, 2, 2, 2)]

    def test_parks_as_queries(self):
        p = Profile(name="test", parks=[ParkQuery("Golden Ears")])
        assert len(p.parks) == 1
        assert p.parks[0].park_query == "Golden Ears"
        assert p.parks[0].map_query is None

    def test_extra_fields_rejected(self):
        with pytest.raises(ValidationError):
            Profile(name="test", patterns=["fri-sun"], unknown=True)

    def test_name_required(self):
        with pytest.raises(ValidationError):
            Profile()

    def test_enabled_default_true(self):
        p = Profile(name="test")
        assert p.enabled is True

    def test_min_start_date_parsed_none(self):
        p = Profile(name="test")
        assert p.min_start_date is None

    def test_min_start_date_parsed_value(self):
        p = Profile(name="test", min_start_date="2026-08-01")
        assert p.min_start_date == "2026-08-01"
