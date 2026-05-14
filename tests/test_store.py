from datetime import date, datetime
from pathlib import Path

from campcli.domain.models import BlockedPark, Booking, Watch
from campcli.infrastructure.store import SqliteStore


class TestSqliteStore:
    def test_round_trip_watch(self, tmp_path):
        store = SqliteStore(tmp_path / "test.db")
        created_at = datetime(2026, 6, 15, 10, 0, 0)
        w = Watch(park_id=1, start_date=date(2026, 7, 1), nights=2, party_size=2, label="test", created_at=created_at)
        saved = store.add_watch(w)
        assert saved.id is not None
        assert saved.created_at == created_at
        rows = store.list_watches()
        assert len(rows) == 1
        assert rows[0].park_id == 1

    def test_remove_watch(self, tmp_path):
        store = SqliteStore(tmp_path / "test.db")
        w = store.add_watch(Watch(park_id=1, start_date=date(2026, 7, 1), nights=2, party_size=1, created_at=datetime(2026, 1, 1, 12, 0, 0)))
        assert w.id is not None
        assert store.remove_watch(w.id) is True
        assert store.list_watches() == []

    def test_round_trip_booking(self, tmp_path):
        store = SqliteStore(tmp_path / "test.db")
        created_at = datetime(2026, 6, 15, 10, 0, 0)
        b = Booking(park_id=1, park_name="Bowron Lake", start_date=date(2026, 8, 1), end_date=date(2026, 8, 3), created_at=created_at)
        saved = store.add_booking(b)
        assert saved.id is not None
        assert saved.created_at == created_at
        rows = store.list_bookings()
        assert len(rows) == 1

    def test_remove_booking(self, tmp_path):
        store = SqliteStore(tmp_path / "test.db")
        b = store.add_booking(Booking(park_id=1, park_name="Bowron Lake", start_date=date(2026, 8, 1), end_date=date(2026, 8, 3), created_at=datetime(2026, 1, 1, 12, 0, 0)))
        assert b.id is not None
        assert store.remove_booking(b.id) is True
        assert store.list_bookings() == []

    def test_round_trip_blocked(self, tmp_path):
        store = SqliteStore(tmp_path / "test.db")
        added_at = datetime(2026, 6, 15, 10, 0, 0)
        bp = BlockedPark(park_id=1, park_name="Bowron Lake", added_at=added_at)
        saved = store.add_blocked(bp)
        assert saved.added_at == added_at
        rows = store.list_blocked()
        assert len(rows) == 1
        assert rows[0].park_id == 1

    def test_remove_blocked(self, tmp_path):
        store = SqliteStore(tmp_path / "test.db")
        store.add_blocked(BlockedPark(park_id=1, park_name="Bowron Lake", added_at=datetime(2026, 1, 1, 12, 0, 0)))
        assert store.remove_blocked(1) is True
        assert store.list_blocked() == []

    def test_settings_round_trip(self, tmp_path):
        store = SqliteStore(tmp_path / "test.db")
        assert store.get_setting("verbose") is None
        store.set_setting("verbose", "on")
        assert store.get_setting("verbose") == "on"
        store.set_setting("verbose", "off")
        assert store.get_setting("verbose") == "off"

    def test_created_at_not_overwritten(self, tmp_path):
        """Adapter must NOT overwrite created_at — Application stamps it."""
        store = SqliteStore(tmp_path / "test.db")
        w = Watch(park_id=1, start_date=date(2026, 7, 1), nights=2, party_size=1, created_at=datetime(2026, 1, 1, 12, 0, 0))
        saved = store.add_watch(w)
        assert saved.created_at == datetime(2026, 1, 1, 12, 0, 0)
