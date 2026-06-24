"""Unit tests for NotInterestedRepo (SqliteStore) using in-memory SQLite."""
from __future__ import annotations

import sqlite3
from datetime import date

import pytest

from campcli.domain.models import NotInterested, Profile
from campcli.infrastructure.store import SqliteStore


@pytest.fixture
def repo(tmp_path):
    return SqliteStore(tmp_path / "test.db")


@pytest.fixture
def profile(repo: SqliteStore) -> Profile:
    return repo.create(Profile(name="test-profile"))


class TestNotInterestedRepo:
    def test_add_and_list_for(self, repo: SqliteStore, profile: Profile):
        repo.add(profile.id, 1, date(2026, 8, 15), date(2026, 8, 17))
        repo.add(profile.id, 2, date(2026, 9, 1), date(2026, 9, 3))
        entries = repo.list_for(profile.id)
        assert len(entries) == 2
        assert entries[0] == NotInterested(profile.id, 1, date(2026, 8, 15), date(2026, 8, 17))

    def test_list_for_empty(self, repo: SqliteStore, profile: Profile):
        assert repo.list_for(profile.id) == []

    def test_list_for_other_profile(self, repo: SqliteStore, profile: Profile):
        repo.add(profile.id, 1, date(2026, 8, 15), date(2026, 8, 17))
        assert repo.list_for(999) == []

    def test_remove_existing(self, repo: SqliteStore, profile: Profile):
        repo.add(profile.id, 1, date(2026, 8, 15), date(2026, 8, 17))
        repo.remove(profile.id, 1, date(2026, 8, 15), date(2026, 8, 17))
        assert repo.list_for(profile.id) == []

    def test_remove_nonexistent_is_noop(self, repo: SqliteStore, profile: Profile):
        repo.remove(profile.id, 1, date(2026, 8, 15), date(2026, 8, 17))
        assert repo.list_for(profile.id) == []

    def test_duplicate_raises_value_error(self, repo: SqliteStore, profile: Profile):
        repo.add(profile.id, 1, date(2026, 8, 15), date(2026, 8, 17))
        with pytest.raises(ValueError, match="already exists"):
            repo.add(profile.id, 1, date(2026, 8, 15), date(2026, 8, 17))

    def test_load_skip_set(self, repo: SqliteStore, profile: Profile):
        repo.add(profile.id, 1, date(2026, 8, 15), date(2026, 8, 17))
        repo.add(profile.id, 2, date(2026, 9, 1), date(2026, 9, 3))
        skip = repo.load_skip_set(profile.id)
        expected = {
            (1, date(2026, 8, 15), date(2026, 8, 17)),
            (2, date(2026, 9, 1), date(2026, 9, 3)),
        }
        assert skip == expected

    def test_load_skip_set_empty(self, repo: SqliteStore, profile: Profile):
        assert repo.load_skip_set(profile.id) == set()

    def test_cascade_delete_profile(self, repo: SqliteStore, profile: Profile):
        repo.add(profile.id, 1, date(2026, 8, 15), date(2026, 8, 17))
        repo.delete(profile.name)
        assert repo.list_for(profile.id) == []

    def test_record_and_lookup_sent(self, repo: SqliteStore, profile: Profile):
        repo.record_sent(100, profile.id, 1, date(2026, 8, 15), date(2026, 8, 17))
        result = repo.lookup_sent(100)
        assert result is not None
        pid, pk, ds, de = result
        assert pid == profile.id
        assert pk == 1
        assert ds == date(2026, 8, 15)
        assert de == date(2026, 8, 17)

    def test_lookup_sent_missing(self, repo: SqliteStore):
        assert repo.lookup_sent(999) is None

    def test_record_sent_multiple(self, repo: SqliteStore, profile: Profile):
        repo.record_sent(100, profile.id, 1, date(2026, 8, 15), date(2026, 8, 17))
        repo.record_sent(101, profile.id, 2, date(2026, 9, 1), date(2026, 9, 3))
        assert repo.lookup_sent(100) is not None
        assert repo.lookup_sent(101) is not None
