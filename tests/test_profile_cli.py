"""Integration tests for `campcli profile` CLI commands."""
from __future__ import annotations

import pytest
from typer.testing import CliRunner

from campcli.composition.cli import app

runner = CliRunner()


class TestProfileCreate:
    def test_create_interactive(self, tmp_path):
        db = tmp_path / "state.db"
        from campcli.composition import cli as cli_mod
        from unittest.mock import patch

        with patch.object(cli_mod, "DB_PATH", db):
            result = runner.invoke(
                app,
                ["profile", "create", "my-profile"],
                input="3\n3.0\n\n14\n",
            )
        assert result.exit_code == 0
        assert "profile 'my-profile' created" in result.stdout

    def test_create_duplicate(self, tmp_path):
        db = tmp_path / "state.db"
        from campcli.composition import cli as cli_mod
        from unittest.mock import patch

        with patch.object(cli_mod, "DB_PATH", db):
            runner.invoke(
                app,
                ["profile", "create", "dup"],
                input="3\n3.0\n\n14\n",
            )
            result = runner.invoke(
                app,
                ["profile", "create", "dup"],
                input="3\n3.0\n\n14\n",
            )
        assert result.exit_code == 2
        assert "already exists" in result.stderr

    def test_create_with_min_start_date(self, tmp_path):
        db = tmp_path / "state.db"
        from campcli.composition import cli as cli_mod
        from unittest.mock import patch

        with patch.object(cli_mod, "DB_PATH", db):
            result = runner.invoke(
                app,
                ["profile", "create", "dated"],
                input="3\n3.0\n2026-07-01\n14\n",
            )
        assert result.exit_code == 0
        assert "created" in result.stdout

    def test_create_with_invalid_date(self, tmp_path):
        db = tmp_path / "state.db"
        from campcli.composition import cli as cli_mod
        from unittest.mock import patch

        with patch.object(cli_mod, "DB_PATH", db):
            result = runner.invoke(
                app,
                ["profile", "create", "bad-date"],
                input="3\n3.0\nnot-a-date\n14\n",
            )
        assert result.exit_code == 2
        assert "invalid date" in result.stderr


class TestProfileList:
    def test_list_empty(self, tmp_path):
        db = tmp_path / "state.db"
        from campcli.composition import cli as cli_mod
        from unittest.mock import patch

        with patch.object(cli_mod, "DB_PATH", db):
            result = runner.invoke(app, ["profile", "list"])
        assert result.exit_code == 0
        assert "no profiles" in result.stdout

    def test_list_with_profiles(self, tmp_path):
        db = tmp_path / "state.db"
        from campcli.composition import cli as cli_mod
        from unittest.mock import patch

        with patch.object(cli_mod, "DB_PATH", db):
            runner.invoke(
                app, ["profile", "create", "alpha"],
                input="6\n2.0\n\n7\n",
            )
            runner.invoke(
                app, ["profile", "create", "beta"],
                input="3\n3.0\n\n14\n",
            )
            result = runner.invoke(app, ["profile", "list"])
        assert result.exit_code == 0
        assert "alpha" in result.stdout
        assert "beta" in result.stdout
        assert "yes" in result.stdout
        assert "6" in result.stdout or "6.0" in result.stdout


class TestProfileShow:
    def test_show_existing(self, tmp_path):
        db = tmp_path / "state.db"
        from campcli.composition import cli as cli_mod
        from unittest.mock import patch

        with patch.object(cli_mod, "DB_PATH", db):
            runner.invoke(
                app, ["profile", "create", "show-me"],
                input="3\n3.0\n\n14\n",
            )
            result = runner.invoke(app, ["profile", "show", "show-me"])
        assert result.exit_code == 0
        assert "show-me" in result.stdout
        assert "max_horizon_months" in result.stdout

    def test_show_missing(self, tmp_path):
        db = tmp_path / "state.db"
        from campcli.composition import cli as cli_mod
        from unittest.mock import patch

        with patch.object(cli_mod, "DB_PATH", db):
            result = runner.invoke(app, ["profile", "show", "ghost"])
        assert result.exit_code == 2
        assert "not found" in result.stderr


class TestProfileEnableDisable:
    def test_enable(self, tmp_path):
        db = tmp_path / "state.db"
        from campcli.composition import cli as cli_mod
        from unittest.mock import patch

        with patch.object(cli_mod, "DB_PATH", db):
            runner.invoke(
                app, ["profile", "create", "switch"],
                input="3\n3.0\n\n14\n",
            )
            result = runner.invoke(app, ["profile", "disable", "switch"])
            assert result.exit_code == 0
            assert "disabled" in result.stdout

            result = runner.invoke(app, ["profile", "enable", "switch"])
            assert result.exit_code == 0
            assert "enabled" in result.stdout

    def test_enable_missing(self, tmp_path):
        db = tmp_path / "state.db"
        from campcli.composition import cli as cli_mod
        from unittest.mock import patch

        with patch.object(cli_mod, "DB_PATH", db):
            result = runner.invoke(app, ["profile", "enable", "ghost"])
        assert result.exit_code == 2
        assert "not found" in result.stderr

    def test_disable_missing(self, tmp_path):
        db = tmp_path / "state.db"
        from campcli.composition import cli as cli_mod
        from unittest.mock import patch

        with patch.object(cli_mod, "DB_PATH", db):
            result = runner.invoke(app, ["profile", "disable", "ghost"])
        assert result.exit_code == 2
        assert "not found" in result.stderr


class TestProfileDelete:
    def test_delete(self, tmp_path):
        db = tmp_path / "state.db"
        from campcli.composition import cli as cli_mod
        from unittest.mock import patch

        with patch.object(cli_mod, "DB_PATH", db):
            runner.invoke(
                app, ["profile", "create", "goner"],
                input="3\n3.0\n\n14\n",
            )
            result = runner.invoke(app, ["profile", "delete", "goner"])
            assert result.exit_code == 0
            assert "deleted" in result.stdout

            # Verify it's gone
            result = runner.invoke(app, ["profile", "list"])
            assert "no profiles" in result.stdout

    def test_delete_missing(self, tmp_path):
        db = tmp_path / "state.db"
        from campcli.composition import cli as cli_mod
        from unittest.mock import patch

        with patch.object(cli_mod, "DB_PATH", db):
            result = runner.invoke(app, ["profile", "delete", "ghost"])
        assert result.exit_code == 2
        assert "not found" in result.stderr
