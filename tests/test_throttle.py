from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import httpx
import pytest
from typer.testing import CliRunner

from campcli.composition.cli import app
from campcli.constants import SETTING_REQUEST_INTERVAL_KEY, read_request_interval, DEFAULT_REQUEST_INTERVAL_SECS
from campcli.infrastructure.api import BCParksClient
from campcli.infrastructure.store import SqliteStore

runner = CliRunner()


class FakeSettingsRepo:
    def __init__(self) -> None:
        self._data: dict[str, str] = {}

    def get_setting(self, key: str) -> str | None:
        return self._data.get(key)

    def set_setting(self, key: str, value: str) -> None:
        self._data[key] = value


class TestRequestIntervalSettingHelper:
    def test_unset_returns_default(self):
        repo = FakeSettingsRepo()
        assert read_request_interval(repo) == DEFAULT_REQUEST_INTERVAL_SECS

    def test_unparseable_returns_default(self):
        repo = FakeSettingsRepo()
        repo.set_setting(SETTING_REQUEST_INTERVAL_KEY, "not-a-float")
        assert read_request_interval(repo) == DEFAULT_REQUEST_INTERVAL_SECS

    def test_valid_value_parsed(self):
        repo = FakeSettingsRepo()
        repo.set_setting(SETTING_REQUEST_INTERVAL_KEY, "8.0")
        assert read_request_interval(repo) == 8.0

    def test_store_round_trip(self, tmp_path):
        store = SqliteStore(tmp_path / "test.db")
        assert store.get_setting(SETTING_REQUEST_INTERVAL_KEY) is None
        store.set_setting(SETTING_REQUEST_INTERVAL_KEY, "5.0")
        assert store.get_setting(SETTING_REQUEST_INTERVAL_KEY) == "5.0"
        assert read_request_interval(store) == 5.0

    def test_store_unset_returns_default(self, tmp_path):
        store = SqliteStore(tmp_path / "test.db")
        assert read_request_interval(store) == DEFAULT_REQUEST_INTERVAL_SECS


class TestBCParksClientThrottle:
    def _make_client(self, interval: float, sleep_recorder: list) -> BCParksClient:
        def fake_sleep(secs: float) -> None:
            sleep_recorder.append(secs)

        mock_http = MagicMock(spec=httpx.Client)
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = [{"resourceLocationId": 1, "localizedValues": [{"fullName": "Test"}]}]
        mock_http.get.return_value = mock_response
        return BCParksClient(client=mock_http, min_interval_secs=interval, sleep=fake_sleep)

    def test_first_call_no_sleep(self):
        recorded: list[float] = []
        client = self._make_client(10.0, recorded)
        client.list_resource_locations()
        assert recorded == []

    def test_subsequent_call_sleeps(self):
        recorded: list[float] = []
        client = self._make_client(10.0, recorded)
        client.list_resource_locations()
        client.list_resource_locations()
        assert len(recorded) == 1
        assert 0 < recorded[0] <= 10.0

    def test_interval_zero_never_sleeps(self):
        recorded: list[float] = []
        client = self._make_client(0, recorded)
        for _ in range(5):
            client.list_resource_locations()
        assert recorded == []

    def test_slow_caller_no_extra_sleep(self):
        recorded: list[float] = []
        client = self._make_client(0.01, recorded)
        client.list_resource_locations()
        client.list_resource_locations()
        assert len(recorded) == 1
        assert 0 <= recorded[0] <= 0.01


class TestCliConfig:
    def test_set_interval(self, tmp_path):
        from campcli.composition import cli as cli_mod
        with patch.object(cli_mod, "DB_PATH", tmp_path / "state.db"):
            result = runner.invoke(app, ["config", "set-interval", "8"])
        assert result.exit_code == 0
        assert "8" in result.stdout
        store = SqliteStore(tmp_path / "state.db")
        assert store.get_setting(SETTING_REQUEST_INTERVAL_KEY) == "8.0"

    def test_set_interval_rejects_zero(self, tmp_path):
        from campcli.composition import cli as cli_mod
        with patch.object(cli_mod, "DB_PATH", tmp_path / "state.db"):
            result = runner.invoke(app, ["config", "set-interval", "0"])
        assert result.exit_code == 1
        assert "must be > 0" in result.stderr
        store = SqliteStore(tmp_path / "state.db")
        assert store.get_setting(SETTING_REQUEST_INTERVAL_KEY) is None

    def test_set_interval_rejects_negative(self, tmp_path):
        from campcli.composition import cli as cli_mod
        with patch.object(cli_mod, "DB_PATH", tmp_path / "state.db"):
            result = runner.invoke(app, ["config", "set-interval", "--", "-1"])
        assert result.exit_code == 1
        assert "must be > 0" in result.stderr

    def test_show_returns_set_value(self, tmp_path):
        from campcli.composition import cli as cli_mod
        with patch.object(cli_mod, "DB_PATH", tmp_path / "state.db"):
            store = SqliteStore(tmp_path / "state.db")
            store.set_setting(SETTING_REQUEST_INTERVAL_KEY, "3.0")
            result = runner.invoke(app, ["config", "show"])
        assert result.exit_code == 0
        assert "3.0" in result.stdout

    def test_show_falls_back_to_default(self, tmp_path):
        from campcli.composition import cli as cli_mod
        with patch.object(cli_mod, "DB_PATH", tmp_path / "state.db"):
            result = runner.invoke(app, ["config", "show"])
        assert result.exit_code == 0
        assert str(DEFAULT_REQUEST_INTERVAL_SECS) in result.stdout
        assert "default" in result.stdout
