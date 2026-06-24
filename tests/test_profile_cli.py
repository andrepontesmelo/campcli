"""Integration tests for `campcli profile` CLI commands."""
from __future__ import annotations

import pytest
from typer.testing import CliRunner

from campcli.composition.cli import app

runner = CliRunner()


_CHILD_INPUT_EMPTY = "\n\n\n\n\n"


class TestProfileCreate:
    def test_create_interactive(self, tmp_path):
        db = tmp_path / "state.db"
        from campcli.composition import cli as cli_mod
        from unittest.mock import patch

        with patch.object(cli_mod, "DB_PATH", db):
            result = runner.invoke(
                app,
                ["profile", "create", "my-profile"],
                input=f"3\n3.0\n\n14\n{_CHILD_INPUT_EMPTY}",
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
                input=f"3\n3.0\n\n14\n{_CHILD_INPUT_EMPTY}",
            )
            result = runner.invoke(
                app,
                ["profile", "create", "dup"],
                input=f"3\n3.0\n\n14\n{_CHILD_INPUT_EMPTY}",
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
                input=f"3\n3.0\n2026-07-01\n14\n{_CHILD_INPUT_EMPTY}",
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

    def test_create_with_children(self, tmp_path):
        db = tmp_path / "state.db"
        from campcli.composition import cli as cli_mod
        from unittest.mock import patch

        with patch.object(cli_mod, "DB_PATH", db):
            result = runner.invoke(
                app,
                ["profile", "create", "full"],
                # 4 core prompts + pattern "fri-sun" + blank + park
                # "Bowron" + blank + tg "12345" + blank
                input=(
                    "3\n3.0\n\n14\n"   # core
                    "fri-sun\n"         # pattern
                    "\n"                # blank = no more patterns
                    "Bowron Lake\n"     # park
                    "\n"                # no map for park
                    "\n"                # blank = no more parks
                    "12345\n"           # tg id
                    "\n"                # blank = no more tg ids
                ),
            )
            assert result.exit_code == 0
            assert "profile 'full' created" in result.stdout

            # Verify children persisted
            result = runner.invoke(app, ["profile", "show", "full"])
            assert result.exit_code == 0
            assert "fri-sun" in result.stdout
            assert "Bowron Lake" in result.stdout
            assert "12345" in result.stdout


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
                input=f"6\n2.0\n\n7\n{_CHILD_INPUT_EMPTY}",
            )
            runner.invoke(
                app, ["profile", "create", "beta"],
                input=f"3\n3.0\n\n14\n{_CHILD_INPUT_EMPTY}",
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
                input=f"3\n3.0\n\n14\n{_CHILD_INPUT_EMPTY}",
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
                input=f"3\n3.0\n\n14\n{_CHILD_INPUT_EMPTY}",
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
                input=f"3\n3.0\n\n14\n{_CHILD_INPUT_EMPTY}",
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


class TestProfileTgCommands:
    def test_tg_add(self, tmp_path):
        db = tmp_path / "state.db"
        from campcli.composition import cli as cli_mod
        from unittest.mock import patch

        with patch.object(cli_mod, "DB_PATH", db):
            runner.invoke(
                app, ["profile", "create", "tg-pro"],
                input=f"3\n3.0\n\n14\n{_CHILD_INPUT_EMPTY}",
            )
            result = runner.invoke(app, ["profile", "tg-add", "tg-pro", "12345"])
        assert result.exit_code == 0
        assert "added" in result.stdout

    def test_tg_add_missing_profile(self, tmp_path):
        db = tmp_path / "state.db"
        from campcli.composition import cli as cli_mod
        from unittest.mock import patch

        with patch.object(cli_mod, "DB_PATH", db):
            result = runner.invoke(app, ["profile", "tg-add", "ghost", "12345"])
        assert result.exit_code == 2
        assert "not found" in result.stderr

    def test_tg_rm(self, tmp_path):
        db = tmp_path / "state.db"
        from campcli.composition import cli as cli_mod
        from unittest.mock import patch

        with patch.object(cli_mod, "DB_PATH", db):
            runner.invoke(
                app, ["profile", "create", "tg-pro"],
                input=f"3\n3.0\n\n14\n{_CHILD_INPUT_EMPTY}",
            )
            runner.invoke(app, ["profile", "tg-add", "tg-pro", "12345"])
            result = runner.invoke(app, ["profile", "tg-rm", "tg-pro", "12345"])
        assert result.exit_code == 0
        assert "removed" in result.stdout

    def test_tg_rm_not_found(self, tmp_path):
        db = tmp_path / "state.db"
        from campcli.composition import cli as cli_mod
        from unittest.mock import patch

        with patch.object(cli_mod, "DB_PATH", db):
            runner.invoke(
                app, ["profile", "create", "tg-pro"],
                input=f"3\n3.0\n\n14\n{_CHILD_INPUT_EMPTY}",
            )
            result = runner.invoke(app, ["profile", "tg-rm", "tg-pro", "99999"])
        assert result.exit_code == 2
        assert "not found" in result.stderr

    def test_tg_list(self, tmp_path):
        db = tmp_path / "state.db"
        from campcli.composition import cli as cli_mod
        from unittest.mock import patch

        with patch.object(cli_mod, "DB_PATH", db):
            runner.invoke(
                app, ["profile", "create", "tg-pro"],
                input=f"3\n3.0\n\n14\n{_CHILD_INPUT_EMPTY}",
            )
            runner.invoke(app, ["profile", "tg-add", "tg-pro", "12345"])
            runner.invoke(app, ["profile", "tg-add", "tg-pro", "67890"])
            result = runner.invoke(app, ["profile", "tg-list", "tg-pro"])
        assert result.exit_code == 0
        assert "12345" in result.stdout
        assert "67890" in result.stdout

    def test_tg_list_empty(self, tmp_path):
        db = tmp_path / "state.db"
        from campcli.composition import cli as cli_mod
        from unittest.mock import patch

        with patch.object(cli_mod, "DB_PATH", db):
            runner.invoke(
                app, ["profile", "create", "tg-pro"],
                input=f"3\n3.0\n\n14\n{_CHILD_INPUT_EMPTY}",
            )
            result = runner.invoke(app, ["profile", "tg-list", "tg-pro"])
        assert result.exit_code == 0
        assert "no Telegram IDs" in result.stdout


class TestProfileEdit:
    def test_edit_add_pattern(self, tmp_path):
        db = tmp_path / "state.db"
        from campcli.composition import cli as cli_mod
        from unittest.mock import patch

        with patch.object(cli_mod, "DB_PATH", db):
            runner.invoke(
                app, ["profile", "create", "edit-me"],
                input=f"3\n3.0\n\n14\n{_CHILD_INPUT_EMPTY}",
            )
            # Choice "1" = add pattern, then "fri-sun", then "7" = done
            result = runner.invoke(
                app,
                ["profile", "edit", "edit-me"],
                input="1\nfri-sun\n7\n",
            )
        assert result.exit_code == 0
        assert "added" in result.stdout

    def test_edit_add_park(self, tmp_path):
        db = tmp_path / "state.db"
        from campcli.composition import cli as cli_mod
        from unittest.mock import patch

        with patch.object(cli_mod, "DB_PATH", db):
            runner.invoke(
                app, ["profile", "create", "edit-me"],
                input=f"3\n3.0\n\n14\n{_CHILD_INPUT_EMPTY}",
            )
            # Choice "3" = add park, "Bowron Lake", no map, "7" = done
            result = runner.invoke(
                app,
                ["profile", "edit", "edit-me"],
                input="3\nBowron Lake\n\n7\n",
            )
        assert result.exit_code == 0
        assert "added" in result.stdout

    def test_edit_add_tg(self, tmp_path):
        db = tmp_path / "state.db"
        from campcli.composition import cli as cli_mod
        from unittest.mock import patch

        with patch.object(cli_mod, "DB_PATH", db):
            runner.invoke(
                app, ["profile", "create", "edit-me"],
                input=f"3\n3.0\n\n14\n{_CHILD_INPUT_EMPTY}",
            )
            # Choice "5" = add tg, "12345", "7" = done
            result = runner.invoke(
                app,
                ["profile", "edit", "edit-me"],
                input="5\n12345\n7\n",
            )
        assert result.exit_code == 0
        assert "added" in result.stdout

    def test_edit_done(self, tmp_path):
        db = tmp_path / "state.db"
        from campcli.composition import cli as cli_mod
        from unittest.mock import patch

        with patch.object(cli_mod, "DB_PATH", db):
            runner.invoke(
                app, ["profile", "create", "edit-me"],
                input=f"3\n3.0\n\n14\n{_CHILD_INPUT_EMPTY}",
            )
            result = runner.invoke(app, ["profile", "edit", "edit-me"], input="7\n")
        assert result.exit_code == 0
        assert "done" in result.stdout
