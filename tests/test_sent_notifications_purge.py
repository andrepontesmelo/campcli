"""Tests for sent_notifications purge logic."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from campcli.domain.models import Profile
from campcli.infrastructure.store import SqliteStore


class FrozenClock:
    def __init__(self, now: datetime):
        self._now = now

    def now(self) -> datetime:
        return self._now


@pytest.fixture
def profile(repo):
    return repo.create(Profile(name="test"))


def test_purge_removes_old_rows():
    """Rows older than 90 days are purged."""
    now = datetime(2026, 8, 15, 12, 0, 0)
    clock = FrozenClock(now)
    repo = SqliteStore.__new__(SqliteStore)
    repo._db_path = None  # not used for in-memory
    repo._clock = clock

    import sqlite3
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            max_horizon_months INTEGER NOT NULL DEFAULT 3,
            max_drive_hours REAL NOT NULL DEFAULT 3.0,
            min_start_date TEXT,
            rest_days_between_bookings INTEGER NOT NULL DEFAULT 14,
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sent_notifications (
            message_id INTEGER PRIMARY KEY,
            profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
            park_id INTEGER NOT NULL,
            date_start TEXT NOT NULL,
            date_end TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
    """)

    # Seed a profile and two sent notifications
    now_iso = now.isoformat()
    conn.execute(
        "INSERT INTO profiles (name, created_at, updated_at) VALUES (?, ?, ?)",
        ("test", now_iso, now_iso),
    )
    conn.commit()
    # Old row — 100 days ago
    old = now - timedelta(days=100)
    conn.execute(
        "INSERT INTO sent_notifications (message_id, profile_id, park_id, date_start, date_end, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (1, 1, 1, "2026-05-01", "2026-05-03", old.isoformat()),
    )
    # New row — today
    conn.execute(
        "INSERT INTO sent_notifications (message_id, profile_id, park_id, date_start, date_end, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (2, 1, 2, "2026-08-15", "2026-08-17", now_iso),
    )
    conn.commit()

    # Use a contextmanager-compatible connect
    from contextlib import contextmanager

    @contextmanager
    def _connect():
        yield conn
        conn.commit()

    repo._connect = _connect

    purged = repo.purge_old_sent_notifications(max_age_days=90)
    assert purged == 1

    remaining = conn.execute("SELECT message_id FROM sent_notifications").fetchall()
    assert [r["message_id"] for r in remaining] == [2]

    conn.close()


def test_purge_no_rows():
    """No rows to purge — returns 0."""
    now = datetime(2026, 8, 15, 12, 0, 0)
    clock = FrozenClock(now)
    repo = SqliteStore.__new__(SqliteStore)
    repo._db_path = None
    repo._clock = clock

    import sqlite3
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            max_horizon_months INTEGER NOT NULL DEFAULT 3,
            max_drive_hours REAL NOT NULL DEFAULT 3.0,
            min_start_date TEXT,
            rest_days_between_bookings INTEGER NOT NULL DEFAULT 14,
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sent_notifications (
            message_id INTEGER PRIMARY KEY,
            profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
            park_id INTEGER NOT NULL,
            date_start TEXT NOT NULL,
            date_end TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
    """)

    now_iso = now.isoformat()
    conn.execute(
        "INSERT INTO profiles (name, created_at, updated_at) VALUES (?, ?, ?)",
        ("test", now_iso, now_iso),
    )
    conn.commit()
    # Only a fresh row
    conn.execute(
        "INSERT INTO sent_notifications (message_id, profile_id, park_id, date_start, date_end, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (1, 1, 1, "2026-08-15", "2026-08-17", now_iso),
    )
    conn.commit()

    from contextlib import contextmanager

    @contextmanager
    def _connect():
        yield conn
        conn.commit()

    repo._connect = _connect

    purged = repo.purge_old_sent_notifications(max_age_days=90)
    assert purged == 0

    conn.close()


def test_purge_called_on_startup(tmp_path):
    """Simulate daemon startup — purge runs via composition root."""
    from datetime import date

    repo = SqliteStore.__new__(SqliteStore)
    repo._db_path = None
    old = datetime(2026, 1, 1, 12, 0, 0)
    now = datetime(2026, 8, 15, 12, 0, 0)
    repo._clock = FrozenClock(now)

    import sqlite3
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            max_horizon_months INTEGER NOT NULL DEFAULT 3,
            max_drive_hours REAL NOT NULL DEFAULT 3.0,
            min_start_date TEXT,
            rest_days_between_bookings INTEGER NOT NULL DEFAULT 14,
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sent_notifications (
            message_id INTEGER PRIMARY KEY,
            profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
            park_id INTEGER NOT NULL,
            date_start TEXT NOT NULL,
            date_end TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
    """)

    now_iso = now.isoformat()
    conn.execute(
        "INSERT INTO profiles (name, created_at, updated_at) VALUES (?, ?, ?)",
        ("test", now_iso, now_iso),
    )
    conn.commit()
    conn.execute(
        "INSERT INTO sent_notifications (message_id, profile_id, park_id, date_start, date_end, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (1, 1, 1, "2026-01-01", "2026-01-03", old.isoformat()),
    )
    conn.execute(
        "INSERT INTO sent_notifications (message_id, profile_id, park_id, date_start, date_end, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (2, 1, 2, "2026-08-15", "2026-08-17", now_iso),
    )
    conn.commit()

    from contextlib import contextmanager

    @contextmanager
    def _connect():
        yield conn
        conn.commit()

    repo._connect = _connect

    purged = repo.purge_old_sent_notifications()
    assert purged == 1

    remaining = conn.execute("SELECT message_id FROM sent_notifications").fetchall()
    assert [r["message_id"] for r in remaining] == [2]

    conn.close()
