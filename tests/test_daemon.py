"""Minimal daemon integration test — verifies migration runs at startup.

The full daemon requires a real Telegram bot token. This test validates the
composition-root wiring: migration runs, profiles are loaded from the DB.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from campcli.application.migrate_profile import migrate_profile_json_to_db


class _FrozenClock:
    def now(self) -> datetime:
        return datetime(2026, 1, 1, 12, 0, 0)


class TestDaemonMigrationWiring:
    def test_migration_called_at_startup(self, tmp_path: Path) -> None:
        """Simulate daemon startup with profile.json present â†' migration occurs."""
        from campcli.domain.models import DriveTimes
        from campcli.domain.models import Profile
        from campcli.infrastructure.store import SqliteStore
        from campcli.application.search_loop import run_search_once
        from campcli.application.search_notifier import SearchNotifier
        from conftest import FakeBCParksApi, FakeTelegram, FakeSearchNotifier

        # Arrange: create profile.json inside a temporary config dir.
        config_dir = tmp_path / ".campcli"
        config_dir.mkdir(parents=True)
        json_path = config_dir / "profile.json"
        json_path.write_text(json.dumps({
            "patterns": ["fri-sun", "sat-sun"],
            "max_horizon_months": 3,
            "max_drive_hours": 3.0,
            "tg_allowed_ids": [12345],
        }))

        db_path = config_dir / "state.db"
        store = SqliteStore(db_path)

        # Act: call migration (same function the daemon calls at startup).
        with patch("campcli.constants.PROFILE_PATH", json_path):
            result = migrate_profile_json_to_db(json_path, store)

        assert result is True
        default = store.get_by_name("default")
        assert default is not None
        assert default.max_horizon_months == 3
        assert default.max_drive_hours == 3.0
        assert default.tg_allowed_ids == [12345]
        assert not json_path.exists()
        assert db_path.exists()

        # --- Search loop wiring check ---
        # Add a park so run_search_once has something to process.
        store.add_park("default", "Bowron Lake")

        fake_api = FakeBCParksApi()
        notifiers: dict[int, SearchNotifier] = {}
        run_search_once(
            api=fake_api,
            profile_repo=store,
            settings_repo=store,
            drive_times=DriveTimes.empty(),
            not_interested_repo=store,
            clock=_FrozenClock(),
            notifier_factory=lambda _: FakeSearchNotifier(),
            notifiers=notifiers,
            log=lambda *a: None,
        )

        assert any(
            call[0] == 1 and call[1] == 10
            for call in fake_api.map_availability_calls
        ), "run_search_once should call map_availability for the migrated profile's park"
