"""SQLite store — single adapter implementing SettingsRepo + ProfileRepo."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from ..domain.models import ParkQuery, PatternSpec, Profile, parse_pattern
from ..domain.ports import Clock
from ..infrastructure.clock import SystemClock


_SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

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

CREATE TABLE IF NOT EXISTS profile_patterns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    pattern TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS profile_parks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    park_query TEXT NOT NULL,
    map_query TEXT
);

CREATE TABLE IF NOT EXISTS profile_telegram_ids (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    tg_id INTEGER NOT NULL
);
"""


class SqliteStore:
    def __init__(self, db_path: Path, clock: Clock | None = None) -> None:
        self._db_path = db_path
        self._clock = clock or SystemClock()
        self._ensure_db()

    def _ensure_db(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._db_path) as conn:
            conn.executescript(_SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # ---- helpers ------------------------------------------------------------

    @staticmethod
    def _row_to_profile(row: sqlite3.Row) -> Profile:
        return Profile(
            id=row["id"],
            name=row["name"],
            max_horizon_months=row["max_horizon_months"],
            max_drive_hours=row["max_drive_hours"],
            min_start_date=row["min_start_date"],
            rest_days_between_bookings=row["rest_days_between_bookings"],
            enabled=bool(row["enabled"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    # ---- SettingsRepo -------------------------------------------------------

    def get_setting(self, key: str) -> str | None:
        with self._connect() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
            return row["value"] if row else None

    def set_setting(self, key: str, value: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                (key, value),
            )

    # ---- child helpers ------------------------------------------------------

    @staticmethod
    def _load_children(conn: sqlite3.Connection, profile: Profile) -> Profile:
        """Load child rows (patterns, parks, tg_ids) for a profile."""
        if profile.id is None:
            return profile
        profile.patterns = [
            parse_pattern(r["pattern"])
            for r in conn.execute(
                "SELECT pattern FROM profile_patterns "
                "WHERE profile_id = ? ORDER BY sort_order",
                (profile.id,),
            ).fetchall()
        ]
        profile.parks = [
            ParkQuery(park_query=r["park_query"], map_query=r["map_query"])
            for r in conn.execute(
                "SELECT park_query, map_query FROM profile_parks "
                "WHERE profile_id = ?",
                (profile.id,),
            ).fetchall()
        ]
        profile.tg_allowed_ids = [
            r["tg_id"]
            for r in conn.execute(
                "SELECT tg_id FROM profile_telegram_ids WHERE profile_id = ?",
                (profile.id,),
            ).fetchall()
        ]
        return profile

    @staticmethod
    def _get_profile_id(conn: sqlite3.Connection, name: str) -> int | None:
        row = conn.execute(
            "SELECT id FROM profiles WHERE name = ?", (name,)
        ).fetchone()
        return row["id"] if row else None

    # ---- ProfileRepo --------------------------------------------------------

    def create(self, profile: Profile) -> Profile:
        now = self._clock.now().isoformat()
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO profiles "
                "(name, max_horizon_months, max_drive_hours, min_start_date, "
                " rest_days_between_bookings, enabled, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    profile.name,
                    profile.max_horizon_months,
                    profile.max_drive_hours,
                    profile.min_start_date,
                    profile.rest_days_between_bookings,
                    int(profile.enabled),
                    now,
                    now,
                ),
            )
            return Profile(
                id=cursor.lastrowid,
                name=profile.name,
                max_horizon_months=profile.max_horizon_months,
                max_drive_hours=profile.max_drive_hours,
                min_start_date=profile.min_start_date,
                rest_days_between_bookings=profile.rest_days_between_bookings,
                enabled=profile.enabled,
                created_at=now,
                updated_at=now,
            )

    def list_all(self) -> list[Profile]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM profiles ORDER BY name"
            ).fetchall()
            return [self._load_children(conn, self._row_to_profile(r)) for r in rows]

    def list_enabled(self) -> list[Profile]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM profiles WHERE enabled = 1 ORDER BY name"
            ).fetchall()
            return [self._load_children(conn, self._row_to_profile(r)) for r in rows]

    def get_by_name(self, name: str) -> Profile | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM profiles WHERE name = ?", (name,)
            ).fetchone()
            if row is None:
                return None
            return self._load_children(conn, self._row_to_profile(row))

    def update(self, profile: Profile) -> Profile:
        now = self._clock.now().isoformat()
        with self._connect() as conn:
            conn.execute(
                "UPDATE profiles SET "
                "max_horizon_months = ?, max_drive_hours = ?, "
                "min_start_date = ?, rest_days_between_bookings = ?, "
                "enabled = ?, updated_at = ? "
                "WHERE name = ?",
                (
                    profile.max_horizon_months,
                    profile.max_drive_hours,
                    profile.min_start_date,
                    profile.rest_days_between_bookings,
                    int(profile.enabled),
                    now,
                    profile.name,
                ),
            )
            return Profile(
                id=profile.id,
                name=profile.name,
                max_horizon_months=profile.max_horizon_months,
                max_drive_hours=profile.max_drive_hours,
                min_start_date=profile.min_start_date,
                rest_days_between_bookings=profile.rest_days_between_bookings,
                enabled=profile.enabled,
                created_at=profile.created_at,
                updated_at=now,
            )

    def delete(self, name: str) -> bool:
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM profiles WHERE name = ?", (name,)
            )
            return cursor.rowcount > 0

    def set_enabled(self, name: str, enabled: bool) -> bool:
        now = self._clock.now().isoformat()
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE profiles SET enabled = ?, updated_at = ? WHERE name = ?",
                (int(enabled), now, name),
            )
            return cursor.rowcount > 0

    # ---- child CRUD --------------------------------------------------------

    def add_pattern(self, profile_name: str, pattern: str, sort_order: int = 0) -> None:
        with self._connect() as conn:
            pid = self._get_profile_id(conn, profile_name)
            if pid is None:
                raise KeyError(f"profile {profile_name!r} not found")
            conn.execute(
                "INSERT INTO profile_patterns (profile_id, pattern, sort_order) VALUES (?, ?, ?)",
                (pid, pattern, sort_order),
            )

    def remove_pattern(self, profile_name: str, pattern: str) -> bool:
        with self._connect() as conn:
            pid = self._get_profile_id(conn, profile_name)
            if pid is None:
                return False
            cursor = conn.execute(
                "DELETE FROM profile_patterns WHERE profile_id = ? AND pattern = ?",
                (pid, pattern),
            )
            return cursor.rowcount > 0

    def list_patterns(self, profile_name: str) -> list[PatternSpec]:
        with self._connect() as conn:
            pid = self._get_profile_id(conn, profile_name)
            if pid is None:
                return []
            return [
                parse_pattern(r["pattern"])
                for r in conn.execute(
                    "SELECT pattern FROM profile_patterns "
                    "WHERE profile_id = ? ORDER BY sort_order",
                    (pid,),
                ).fetchall()
            ]

    def add_park(self, profile_name: str, park_query: str, map_query: str | None = None) -> None:
        with self._connect() as conn:
            pid = self._get_profile_id(conn, profile_name)
            if pid is None:
                raise KeyError(f"profile {profile_name!r} not found")
            conn.execute(
                "INSERT INTO profile_parks (profile_id, park_query, map_query) VALUES (?, ?, ?)",
                (pid, park_query, map_query),
            )

    def remove_park(self, profile_name: str, park_query: str) -> bool:
        with self._connect() as conn:
            pid = self._get_profile_id(conn, profile_name)
            if pid is None:
                return False
            cursor = conn.execute(
                "DELETE FROM profile_parks WHERE profile_id = ? AND park_query = ?",
                (pid, park_query),
            )
            return cursor.rowcount > 0

    def list_parks(self, profile_name: str) -> list[ParkQuery]:
        with self._connect() as conn:
            pid = self._get_profile_id(conn, profile_name)
            if pid is None:
                return []
            return [
                ParkQuery(park_query=r["park_query"], map_query=r["map_query"])
                for r in conn.execute(
                    "SELECT park_query, map_query FROM profile_parks WHERE profile_id = ?",
                    (pid,),
                ).fetchall()
            ]

    def add_tg_id(self, profile_name: str, tg_id: int) -> None:
        with self._connect() as conn:
            pid = self._get_profile_id(conn, profile_name)
            if pid is None:
                raise KeyError(f"profile {profile_name!r} not found")
            conn.execute(
                "INSERT INTO profile_telegram_ids (profile_id, tg_id) VALUES (?, ?)",
                (pid, tg_id),
            )

    def remove_tg_id(self, profile_name: str, tg_id: int) -> bool:
        with self._connect() as conn:
            pid = self._get_profile_id(conn, profile_name)
            if pid is None:
                return False
            cursor = conn.execute(
                "DELETE FROM profile_telegram_ids WHERE profile_id = ? AND tg_id = ?",
                (pid, tg_id),
            )
            return cursor.rowcount > 0

    def list_tg_ids(self, profile_name: str) -> list[int]:
        with self._connect() as conn:
            pid = self._get_profile_id(conn, profile_name)
            if pid is None:
                return []
            return [
                r["tg_id"]
                for r in conn.execute(
                    "SELECT tg_id FROM profile_telegram_ids WHERE profile_id = ?",
                    (pid,),
                ).fetchall()
            ]
