"""Tests for CLI telegram allow/revoke/list subcommands."""
from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from campcli.composition.cli import app

runner = CliRunner()


class TestTelegramAllow:
    def test_add_id_to_empty_list(self, tmp_path):
        profile = tmp_path / "profile.json"
        profile.write_text(json.dumps({"tg_allowed_ids": []}) + "\n")
        from campcli.composition import cli as cli_mod
        from unittest.mock import patch
        with patch.object(cli_mod, "CONFIG_DIR", tmp_path):
            result = runner.invoke(app, ["telegram", "allow", "12345"])
        assert result.exit_code == 0
        data = json.loads(profile.read_text())
        assert data["tg_allowed_ids"] == [12345]
        assert "authorized" in result.stdout

    def test_add_multiple_ids(self, tmp_path):
        profile = tmp_path / "profile.json"
        profile.write_text(json.dumps({"tg_allowed_ids": []}) + "\n")
        from campcli.composition import cli as cli_mod
        from unittest.mock import patch
        with patch.object(cli_mod, "CONFIG_DIR", tmp_path):
            result = runner.invoke(app, ["telegram", "allow", "12345", "67890"])
        assert result.exit_code == 0
        data = json.loads(profile.read_text())
        assert data["tg_allowed_ids"] == [12345, 67890]

    def test_duplicate_id_no_op(self, tmp_path):
        profile = tmp_path / "profile.json"
        profile.write_text(json.dumps({"tg_allowed_ids": [12345]}) + "\n")
        from campcli.composition import cli as cli_mod
        from unittest.mock import patch
        with patch.object(cli_mod, "CONFIG_DIR", tmp_path):
            result = runner.invoke(app, ["telegram", "allow", "12345"])
        assert result.exit_code == 0
        assert "already authorized" in result.stdout
        data = json.loads(profile.read_text())
        assert data["tg_allowed_ids"] == [12345]

    def test_missing_profile_exits_with_code_2(self, tmp_path):
        from campcli.composition import cli as cli_mod
        from unittest.mock import patch
        with patch.object(cli_mod, "CONFIG_DIR", tmp_path):
            result = runner.invoke(app, ["telegram", "allow", "12345"])
        assert result.exit_code == 2
        assert "profile.json not found" in result.stderr


class TestTelegramRevoke:
    def test_revoke_existing_id(self, tmp_path):
        profile = tmp_path / "profile.json"
        profile.write_text(json.dumps({"tg_allowed_ids": [12345, 67890]}) + "\n")
        from campcli.composition import cli as cli_mod
        from unittest.mock import patch
        with patch.object(cli_mod, "CONFIG_DIR", tmp_path):
            result = runner.invoke(app, ["telegram", "revoke", "12345"])
        assert result.exit_code == 0
        data = json.loads(profile.read_text())
        assert data["tg_allowed_ids"] == [67890]
        assert "revoked" in result.stdout

    def test_revoke_not_found(self, tmp_path):
        profile = tmp_path / "profile.json"
        profile.write_text(json.dumps({"tg_allowed_ids": [12345]}) + "\n")
        from campcli.composition import cli as cli_mod
        from unittest.mock import patch
        with patch.object(cli_mod, "CONFIG_DIR", tmp_path):
            result = runner.invoke(app, ["telegram", "revoke", "99999"])
        assert result.exit_code == 0
        assert "not found" in result.stdout
        data = json.loads(profile.read_text())
        assert data["tg_allowed_ids"] == [12345]

    def test_missing_profile_exits_with_code_2(self, tmp_path):
        from campcli.composition import cli as cli_mod
        from unittest.mock import patch
        with patch.object(cli_mod, "CONFIG_DIR", tmp_path):
            result = runner.invoke(app, ["telegram", "revoke", "12345"])
        assert result.exit_code == 2
        assert "profile.json not found" in result.stderr


class TestTelegramList:
    def test_list_authorized_ids(self, tmp_path):
        profile = tmp_path / "profile.json"
        profile.write_text(json.dumps({"tg_allowed_ids": [12345, 67890]}) + "\n")
        from campcli.composition import cli as cli_mod
        from unittest.mock import patch
        with patch.object(cli_mod, "CONFIG_DIR", tmp_path):
            result = runner.invoke(app, ["telegram", "list"])
        assert result.exit_code == 0
        assert "12345" in result.stdout
        assert "67890" in result.stdout

    def test_list_empty(self, tmp_path):
        profile = tmp_path / "profile.json"
        profile.write_text(json.dumps({"tg_allowed_ids": []}) + "\n")
        from campcli.composition import cli as cli_mod
        from unittest.mock import patch
        with patch.object(cli_mod, "CONFIG_DIR", tmp_path):
            result = runner.invoke(app, ["telegram", "list"])
        assert result.exit_code == 0
        assert "no authorized telegram users" in result.stdout

    def test_missing_profile_exits_with_code_2(self, tmp_path):
        from campcli.composition import cli as cli_mod
        from unittest.mock import patch
        with patch.object(cli_mod, "CONFIG_DIR", tmp_path):
            result = runner.invoke(app, ["telegram", "list"])
        assert result.exit_code == 2
        assert "profile.json not found" in result.stderr
