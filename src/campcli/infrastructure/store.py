"""SQLite store — single adapter implementing WatchRepo, BookingRepo, BlockedParkRepo, SettingsRepo."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Iterator

from ..domain.models import BlockedPark, Booking, Watch

_SCHEMA = """
CREATE TABLE IF NOT EXISTS watches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    park_id INTEGER NOT NULL,
    start_date TEXT NOT NULL,
    nights INTEGER NOT NULL,
    party_size INTEGER NOT NULL DEFAULT 1,
    label TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS bookings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    park_id INTEGER NOT NULL,
    park_name TEXT NOT NULL,
    map_name TEXT,
    site_name TEXT,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    party_size INTEGER,
    fee REAL,
    notes TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS blocked_parks (
    park_id INTEGER PRIMARY KEY,
    park_name TEXT NOT NULL,
    added_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


class SqliteStore:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._ensure_db()

    def _ensure_db(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._db_path) as conn:
            conn.executescript(_SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # ---- helpers ------------------------------------------------------------

    @staticmethod
    def _row_to_watch(row: sqlite3.Row) -> Watch:
        return Watch(
            id=row["id"],
            park_id=row["park_id"],
            start_date=date.fromisoformat(row["start_date"]),
            nights=row["nights"],
            party_size=row["party_size"],
            label=row["label"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    @staticmethod
    def _row_to_booking(row: sqlite3.Row) -> Booking:
        return Booking(
            id=row["id"],
            park_id=row["park_id"],
            park_name=row["park_name"],
            map_name=row["map_name"],
            site_name=row["site_name"],
            start_date=date.fromisoformat(row["start_date"]),
            end_date=date.fromisoformat(row["end_date"]),
            party_size=row["party_size"],
            fee=row["fee"],
            notes=row["notes"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    @staticmethod
    def _row_to_blocked(row: sqlite3.Row) -> BlockedPark:
        return BlockedPark(
            park_id=row["park_id"],
            park_name=row["park_name"],
            added_at=datetime.fromisoformat(row["added_at"]),
        )

    # ---- WatchRepo ----------------------------------------------------------

    def add_watch(self, watch: Watch) -> Watch:
        if watch.created_at is None:
            raise ValueError("Watch.created_at must be set by Application before persisting")
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO watches (park_id, start_date, nights, party_size, label, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    watch.park_id,
                    watch.start_date.isoformat(),
                    watch.nights,
                    watch.party_size,
                    watch.label,
                    watch.created_at.isoformat(timespec="seconds"),
                ),
            )
            row = conn.execute("SELECT * FROM watches WHERE id = ?", (cur.lastrowid,)).fetchone()
            return self._row_to_watch(row)

    def list_watches(self) -> list[Watch]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM watches ORDER BY id").fetchall()
            return [self._row_to_watch(r) for r in rows]

    def remove_watch(self, watch_id: int) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM watches WHERE id = ?", (watch_id,))
            return cur.rowcount > 0

    # ---- BookingRepo --------------------------------------------------------

    def add_booking(self, booking: Booking) -> Booking:
        if booking.created_at is None:
            raise ValueError("Booking.created_at must be set by Application before persisting")
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO bookings (park_id, park_name, map_name, site_name, "
                "start_date, end_date, party_size, fee, notes, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    booking.park_id,
                    booking.park_name,
                    booking.map_name,
                    booking.site_name,
                    booking.start_date.isoformat(),
                    booking.end_date.isoformat(),
                    booking.party_size,
                    booking.fee,
                    booking.notes,
                    booking.created_at.isoformat(timespec="seconds"),
                ),
            )
            row = conn.execute("SELECT * FROM bookings WHERE id = ?", (cur.lastrowid,)).fetchone()
            return self._row_to_booking(row)

    def list_bookings(self) -> list[Booking]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM bookings ORDER BY start_date").fetchall()
            return [self._row_to_booking(r) for r in rows]

    def remove_booking(self, booking_id: int) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM bookings WHERE id = ?", (booking_id,))
            return cur.rowcount > 0

    # ---- BlockedParkRepo ----------------------------------------------------

    def add_blocked(self, blocked: BlockedPark) -> BlockedPark:
        if blocked.added_at is None:
            raise ValueError("BlockedPark.added_at must be set by Application before persisting")
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO blocked_parks (park_id, park_name, added_at) "
                "VALUES (?, ?, ?)",
                (blocked.park_id, blocked.park_name, blocked.added_at.isoformat(timespec="seconds")),
            )
            row = conn.execute(
                "SELECT * FROM blocked_parks WHERE park_id = ?", (blocked.park_id,)
            ).fetchone()
            return self._row_to_blocked(row)

    def list_blocked(self) -> list[BlockedPark]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM blocked_parks ORDER BY park_name").fetchall()
            return [self._row_to_blocked(r) for r in rows]

    def remove_blocked(self, park_id: int) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM blocked_parks WHERE park_id = ?", (park_id,))
            return cur.rowcount > 0

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
