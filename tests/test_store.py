from campcli.infrastructure.store import SqliteStore


class TestSqliteStore:
    def test_settings_round_trip(self, tmp_path):
        store = SqliteStore(tmp_path / "test.db")
        assert store.get_setting("verbose") is None
        store.set_setting("verbose", "on")
        assert store.get_setting("verbose") == "on"
        store.set_setting("verbose", "off")
        assert store.get_setting("verbose") == "off"
