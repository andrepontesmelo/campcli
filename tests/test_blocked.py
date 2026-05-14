from datetime import datetime

from campcli.application import blocked
from campcli.domain.models import BlockedPark


class TestBlockedRemove:
    def test_remove_by_id(self, fake_api, store):
        store.add_blocked(BlockedPark(park_id=1, park_name="Bowron Lake", added_at=datetime(2026, 1, 1, 12, 0, 0)))
        assert blocked.remove(fake_api, "1", blocked_repo=store) is True
        assert store.list_blocked() == []

    def test_remove_by_name(self, fake_api, store):
        store.add_blocked(BlockedPark(park_id=1, park_name="Bowron Lake", added_at=datetime(2026, 1, 1, 12, 0, 0)))
        assert blocked.remove(fake_api, "bowron", blocked_repo=store) is True
        assert store.list_blocked() == []

    def test_remove_nonexistent(self, fake_api, store):
        assert blocked.remove(fake_api, "9999", blocked_repo=store) is False


class TestBlockedAdd:
    def test_add_parks(self, fake_api, store, clock):
        bp = blocked.add(fake_api, "bowron", blocked_repo=store, clock=clock)
        assert bp.park_name == "Bowron Lake"
        assert bp.park_id == 1
        rows = store.list_blocked()
        assert len(rows) == 1
        assert rows[0].park_name == "Bowron Lake"
