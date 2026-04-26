"""SQLite store for watches. Simple, single table, no migrations yet."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from typing import Iterator

from .constants import CONFIG_DIR, DB_PATH
from .models import BlockedPark, Booking, Watch

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
"""


def _ensure_db() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.executescript(_SCHEMA)


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    _ensure_db()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


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


def add_watch(w: Watch) -> Watch:
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO watches (park_id, start_date, nights, party_size, label, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                w.park_id,
                w.start_date.isoformat(),
                w.nights,
                w.party_size,
                w.label,
                datetime.now().isoformat(timespec="seconds"),
            ),
        )
        watch_id = cur.lastrowid
        row = conn.execute("SELECT * FROM watches WHERE id = ?", (watch_id,)).fetchone()
        return _row_to_watch(row)


def list_watches() -> list[Watch]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM watches ORDER BY id").fetchall()
        return [_row_to_watch(r) for r in rows]


def remove_watch(watch_id: int) -> bool:
    with connect() as conn:
        cur = conn.execute("DELETE FROM watches WHERE id = ?", (watch_id,))
        return cur.rowcount > 0


# ----- bookings --------------------------------------------------------------

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


def add_booking(b: Booking) -> Booking:
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO bookings (park_id, park_name, map_name, site_name, "
            "start_date, end_date, party_size, fee, notes, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                b.park_id,
                b.park_name,
                b.map_name,
                b.site_name,
                b.start_date.isoformat(),
                b.end_date.isoformat(),
                b.party_size,
                b.fee,
                b.notes,
                datetime.now().isoformat(timespec="seconds"),
            ),
        )
        row = conn.execute("SELECT * FROM bookings WHERE id = ?", (cur.lastrowid,)).fetchone()
        return _row_to_booking(row)


def list_bookings() -> list[Booking]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM bookings ORDER BY start_date").fetchall()
        return [_row_to_booking(r) for r in rows]


def remove_booking(booking_id: int) -> bool:
    with connect() as conn:
        cur = conn.execute("DELETE FROM bookings WHERE id = ?", (booking_id,))
        return cur.rowcount > 0


# ----- blocked parks ---------------------------------------------------------

def _row_to_blocked(row: sqlite3.Row) -> BlockedPark:
    return BlockedPark(
        park_id=row["park_id"],
        park_name=row["park_name"],
        added_at=datetime.fromisoformat(row["added_at"]),
    )


def add_blocked_park(park_id: int, park_name: str) -> BlockedPark:
    with connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO blocked_parks (park_id, park_name, added_at) "
            "VALUES (?, ?, ?)",
            (park_id, park_name, datetime.now().isoformat(timespec="seconds")),
        )
        row = conn.execute("SELECT * FROM blocked_parks WHERE park_id = ?", (park_id,)).fetchone()
        return _row_to_blocked(row)


def list_blocked_parks() -> list[BlockedPark]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM blocked_parks ORDER BY park_name").fetchall()
        return [_row_to_blocked(r) for r in rows]


def remove_blocked_park(park_id: int) -> bool:
    with connect() as conn:
        cur = conn.execute("DELETE FROM blocked_parks WHERE park_id = ?", (park_id,))
        return cur.rowcount > 0
