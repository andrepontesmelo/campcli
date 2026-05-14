from campcli import blocked, store


class TestBlockedRemove:
    def test_remove_by_id(self, fake_api, tmp_db):
        store.add_blocked_park(1, "Bowron Lake")
        assert blocked.remove(fake_api, "1") is True
        assert store.list_blocked_parks() == []

    def test_remove_by_name(self, fake_api, tmp_db):
        store.add_blocked_park(1, "Bowron Lake")
        assert blocked.remove(fake_api, "bowron") is True
        assert store.list_blocked_parks() == []

    def test_remove_nonexistent(self, fake_api, tmp_db):
        assert blocked.remove(fake_api, "9999") is False


class TestBlockedAdd:
    def test_add_parks(self, fake_api, tmp_db):
        bp = blocked.add(fake_api, "bowron")
        assert bp.park_name == "Bowron Lake"
        assert bp.park_id == 1
        rows = store.list_blocked_parks()
        assert len(rows) == 1
        assert rows[0].park_name == "Bowron Lake"
