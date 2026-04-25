"""SQLite store for watches. Simple, single table, no migrations yet."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from typing import Iterator

from .constants import CONFIG_DIR, DB_PATH
from .models import Watch

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
