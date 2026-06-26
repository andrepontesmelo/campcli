"""Integration tests for `campcli profile` CLI commands."""
from __future__ import annotations

import json

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


class TestSearchProfileAware:
    """Tests for profile-aware CLI search commands."""

    def test_search_with_profile_flag(self, tmp_path, fake_api):
        """campcli search --profile weekend-only runs against that profile's parks."""
        db = tmp_path / "state.db"
        from campcli.composition import cli as cli_mod
        from campcli.application.drive_times import DriveTimes
        from unittest.mock import patch

        with patch.object(cli_mod, "DB_PATH", db):
            runner.invoke(
                app, ["profile", "create", "weekend-only"],
                input="3\n3.0\n\n14\nfri-sun\n\nBowron Lake\n\n\n",
            )

            with patch.object(cli_mod, "api_call") as mock_api:
                mock_api.return_value.__enter__.return_value = fake_api
                with patch.object(cli_mod, "load_drive_times", return_value=DriveTimes.empty()):
                    result = runner.invoke(app, ["search", "--profile", "weekend-only"])

        assert result.exit_code in (0, 3)
        assert "Profile: weekend-only" in result.stderr

    def test_search_auto_selects_single_enabled(self, tmp_path, fake_api):
        """Exactly 1 enabled profile → auto-select, no error."""
        db = tmp_path / "state.db"
        from campcli.composition import cli as cli_mod
        from campcli.application.drive_times import DriveTimes
        from unittest.mock import patch

        with patch.object(cli_mod, "DB_PATH", db):
            runner.invoke(
                app, ["profile", "create", "solo"],
                input="3\n3.0\n\n14\n\n\n\n",
            )

            with patch.object(cli_mod, "api_call") as mock_api:
                mock_api.return_value.__enter__.return_value = fake_api
                with patch.object(cli_mod, "load_drive_times", return_value=DriveTimes.empty()):
                    result = runner.invoke(app, ["search"])

        assert result.exit_code in (0, 3)
        assert "Profile: solo" in result.stderr

    def test_search_no_enabled_profiles_errors(self, tmp_path):
        """0 enabled → clear error."""
        db = tmp_path / "state.db"
        from campcli.composition import cli as cli_mod
        from unittest.mock import patch

        with patch.object(cli_mod, "DB_PATH", db):
            runner.invoke(
                app, ["profile", "create", "offline"],
                input="3\n3.0\n\n14\n\n\n\n",
            )
            runner.invoke(app, ["profile", "disable", "offline"])

            result = runner.invoke(app, ["search"])

        assert result.exit_code == 2
        assert "no enabled profiles found" in result.stderr

    def test_search_multiple_enabled_errors(self, tmp_path):
        """2+ enabled → error mentioning --profile."""
        db = tmp_path / "state.db"
        from campcli.composition import cli as cli_mod
        from unittest.mock import patch

        with patch.object(cli_mod, "DB_PATH", db):
            runner.invoke(
                app, ["profile", "create", "alpha"],
                input="3\n3.0\n\n14\n\n\n\n",
            )
            runner.invoke(
                app, ["profile", "create", "beta"],
                input="6\n2.0\n\n7\n\n\n\n",
            )

            result = runner.invoke(app, ["search"])

        assert result.exit_code == 2
        assert "--profile" in result.stderr

    def test_search_unknown_profile_errors(self, tmp_path):
        """--profile nonexistent → clear error."""
        db = tmp_path / "state.db"
        from campcli.composition import cli as cli_mod
        from unittest.mock import patch

        with patch.object(cli_mod, "DB_PATH", db):
            result = runner.invoke(app, ["search", "--profile", "nonexistent"])

        assert result.exit_code == 2
        assert "not found" in result.stderr

    def test_check_with_profile_flag(self, tmp_path, fake_api):
        """campcli check --profile weekend-only resolves the profile."""
        db = tmp_path / "state.db"
        from campcli.composition import cli as cli_mod
        from unittest.mock import patch

        with patch.object(cli_mod, "DB_PATH", db):
            runner.invoke(
                app, ["profile", "create", "weekend-only"],
                input="3\n3.0\n\n14\nfri-sun\n\nBowron Lake\n\n\n",
            )

            with patch.object(cli_mod, "api_call") as mock_api:
                mock_api.return_value.__enter__.return_value = fake_api
                result = runner.invoke(app, [
                    "check", "--park", "1", "--start", "2026-07-01",
                    "--nights", "2", "--profile", "weekend-only",
                ])

        assert result.exit_code in (0, 3)

    def test_profile_search_command(self, tmp_path, fake_api):
        """campcli profile search weekend-only is the explicit form."""
        db = tmp_path / "state.db"
        from campcli.composition import cli as cli_mod
        from campcli.application.drive_times import DriveTimes
        from unittest.mock import patch

        with patch.object(cli_mod, "DB_PATH", db):
            runner.invoke(
                app, ["profile", "create", "weekend-only"],
                input="3\n3.0\n\n14\nfri-sun\n\nBowron Lake\n\n\n",
            )

            with patch.object(cli_mod, "api_call") as mock_api:
                mock_api.return_value.__enter__.return_value = fake_api
                with patch.object(cli_mod, "load_drive_times", return_value=DriveTimes.empty()):
                    result = runner.invoke(app, ["profile", "search", "weekend-only"])

        assert result.exit_code in (0, 3)
        assert "Profile: weekend-only" in result.stderr

    def test_profile_search_disabled_errors(self, tmp_path):
        """Searching a disabled profile errors clearly."""
        db = tmp_path / "state.db"
        from campcli.composition import cli as cli_mod
        from unittest.mock import patch

        with patch.object(cli_mod, "DB_PATH", db):
            runner.invoke(
                app, ["profile", "create", "disabled-one"],
                input="3\n3.0\n\n14\n\n\n\n",
            )
            runner.invoke(app, ["profile", "disable", "disabled-one"])

            result = runner.invoke(app, ["profile", "search", "disabled-one"])

        assert result.exit_code == 2
        assert "is disabled" in result.stderr

    def test_profile_search_missing_errors(self, tmp_path):
        """Searching a non-existent profile errors clearly."""
        db = tmp_path / "state.db"
        from campcli.composition import cli as cli_mod
        from unittest.mock import patch

        with patch.object(cli_mod, "DB_PATH", db):
            result = runner.invoke(app, ["profile", "search", "ghost"])

        assert result.exit_code == 2
        assert "not found" in result.stderr

    def test_search_migrates_and_auto_selects(self, tmp_path, fake_api):
        """With profile.json + empty DB → search auto-selects migrated 'default'."""
        db = tmp_path / "state.db"
        profile_json = tmp_path / "profile.json"
        profile_json.write_text(json.dumps({
            "max_horizon_months": 3,
            "max_drive_hours": 3.0,
            "patterns": ["fri-sun"],
            "allowed": [{"park": "Bowron Lake"}],
        }))

        from campcli.composition import cli as cli_mod
        from campcli.application.drive_times import DriveTimes
        from unittest.mock import patch

        with patch.object(cli_mod, "DB_PATH", db):
            with patch.object(cli_mod, "PROFILE_PATH", profile_json):
                with patch.object(cli_mod, "api_call") as mock_api:
                    mock_api.return_value.__enter__.return_value = fake_api
                    with patch.object(cli_mod, "load_drive_times", return_value=DriveTimes.empty()):
                        result = runner.invoke(app, ["search"])

        assert result.exit_code in (0, 3)
        assert "Profile: default" in result.stderr

    def test_search_with_disabled_profile_errors(self, tmp_path):
        """--profile disabled → error."""
        db = tmp_path / "state.db"
        from campcli.composition import cli as cli_mod
        from unittest.mock import patch

        with patch.object(cli_mod, "DB_PATH", db):
            runner.invoke(
                app, ["profile", "create", "disabled"],
                input="3\n3.0\n\n14\n\n\n\n",
            )
            runner.invoke(app, ["profile", "disable", "disabled"])

            result = runner.invoke(app, ["search", "--profile", "disabled"])

        assert result.exit_code == 2
        assert "is disabled" in result.stderr

    def test_check_with_disabled_profile_errors(self, tmp_path):
        """campcli check --profile disabled → error."""
        db = tmp_path / "state.db"
        from campcli.composition import cli as cli_mod
        from unittest.mock import patch

        with patch.object(cli_mod, "DB_PATH", db):
            runner.invoke(
                app, ["profile", "create", "disabled"],
                input="3\n3.0\n\n14\n\n\n\n",
            )
            runner.invoke(app, ["profile", "disable", "disabled"])

            result = runner.invoke(app, [
                "check", "--park", "1", "--start", "2026-07-01",
                "--nights", "2", "--profile", "disabled",
            ])

        assert result.exit_code == 2
        assert "is disabled" in result.stderr

    def test_check_with_unknown_profile_errors(self, tmp_path):
        """campcli check --profile nonexistent → error."""
        db = tmp_path / "state.db"
        from campcli.composition import cli as cli_mod
        from unittest.mock import patch

        with patch.object(cli_mod, "DB_PATH", db):
            result = runner.invoke(app, [
                "check", "--park", "1", "--start", "2026-07-01",
                "--nights", "2", "--profile", "nonexistent",
            ])

        assert result.exit_code == 2
        assert "not found" in result.stderr


class TestNotInterestedCli:
    """Tests for ``campcli profile not-interested`` commands."""

    def test_add_success(self, tmp_path, fake_api):
        db = tmp_path / "state.db"
        from campcli.composition import cli as cli_mod
        from unittest.mock import patch

        with patch.object(cli_mod, "DB_PATH", db):
            runner.invoke(
                app, ["profile", "create", "test"],
                input="3\n3.0\n\n14\n\n\n\n",
            )
            with patch.object(cli_mod, "api_call") as mock_api:
                mock_api.return_value.__enter__.return_value = fake_api
                result = runner.invoke(app, [
                    "profile", "not-interested", "add",
                    "test", "Bowron Lake", "2026-07-01", "2026-07-03",
                ])
        assert result.exit_code == 0
        assert "Marked Bowron Lake as not interested" in result.stdout
        assert "2026-07-01" in result.stdout
        assert "2026-07-03" in result.stdout

    def test_add_duplicate(self, tmp_path, fake_api):
        db = tmp_path / "state.db"
        from campcli.composition import cli as cli_mod
        from unittest.mock import patch

        with patch.object(cli_mod, "DB_PATH", db):
            runner.invoke(
                app, ["profile", "create", "test"],
                input="3\n3.0\n\n14\n\n\n\n",
            )
            with patch.object(cli_mod, "api_call") as mock_api:
                mock_api.return_value.__enter__.return_value = fake_api
                runner.invoke(app, [
                    "profile", "not-interested", "add",
                    "test", "Bowron Lake", "2026-07-01", "2026-07-03",
                ])
                result = runner.invoke(app, [
                    "profile", "not-interested", "add",
                    "test", "Bowron Lake", "2026-07-01", "2026-07-03",
                ])
        assert result.exit_code == 2
        assert "Already marked not interested" in result.stderr

    def test_add_unknown_profile(self, tmp_path):
        db = tmp_path / "state.db"
        from campcli.composition import cli as cli_mod
        from unittest.mock import patch

        with patch.object(cli_mod, "DB_PATH", db):
            result = runner.invoke(app, [
                "profile", "not-interested", "add",
                "nonexistent", "Bowron Lake", "2026-07-01", "2026-07-03",
            ])
        assert result.exit_code == 2
        assert "not found" in result.stderr

    def test_add_unknown_park(self, tmp_path, fake_api):
        db = tmp_path / "state.db"
        from campcli.composition import cli as cli_mod
        from unittest.mock import patch

        with patch.object(cli_mod, "DB_PATH", db):
            runner.invoke(
                app, ["profile", "create", "test"],
                input="3\n3.0\n\n14\n\n\n\n",
            )
            with patch.object(cli_mod, "api_call") as mock_api:
                mock_api.return_value.__enter__.return_value = fake_api
                result = runner.invoke(app, [
                    "profile", "not-interested", "add",
                    "test", "NoSuchPark", "2026-07-01", "2026-07-03",
                ])
        assert result.exit_code == 2
        assert "no park matches" in result.stderr

    def test_add_invalid_date(self, tmp_path):
        db = tmp_path / "state.db"
        from campcli.composition import cli as cli_mod
        from unittest.mock import patch

        with patch.object(cli_mod, "DB_PATH", db):
            runner.invoke(
                app, ["profile", "create", "test"],
                input="3\n3.0\n\n14\n\n\n\n",
            )
            result = runner.invoke(app, [
                "profile", "not-interested", "add",
                "test", "Bowron Lake", "not-a-date", "2026-07-03",
            ])
        assert result.exit_code == 2
        assert "invalid date" in result.stderr

    def test_add_date_order_violation(self, tmp_path):
        db = tmp_path / "state.db"
        from campcli.composition import cli as cli_mod
        from unittest.mock import patch

        with patch.object(cli_mod, "DB_PATH", db):
            runner.invoke(
                app, ["profile", "create", "test"],
                input="3\n3.0\n\n14\n\n\n\n",
            )
            result = runner.invoke(app, [
                "profile", "not-interested", "add",
                "test", "Bowron Lake", "2026-07-05", "2026-07-03",
            ])
        assert result.exit_code == 2
        assert "date_start must not be after date_end" in result.stderr

    def test_rm_success(self, tmp_path, fake_api):
        db = tmp_path / "state.db"
        from campcli.composition import cli as cli_mod
        from unittest.mock import patch

        with patch.object(cli_mod, "DB_PATH", db):
            runner.invoke(
                app, ["profile", "create", "test"],
                input="3\n3.0\n\n14\n\n\n\n",
            )
            with patch.object(cli_mod, "api_call") as mock_api:
                mock_api.return_value.__enter__.return_value = fake_api
                runner.invoke(app, [
                    "profile", "not-interested", "add",
                    "test", "Bowron Lake", "2026-07-01", "2026-07-03",
                ])
                result = runner.invoke(app, [
                    "profile", "not-interested", "rm",
                    "test", "Bowron Lake", "2026-07-01", "2026-07-03",
                ])
        assert result.exit_code == 0
        assert "Removed not-interested" in result.stdout

    def test_rm_nonexistent(self, tmp_path, fake_api):
        db = tmp_path / "state.db"
        from campcli.composition import cli as cli_mod
        from unittest.mock import patch

        with patch.object(cli_mod, "DB_PATH", db):
            runner.invoke(
                app, ["profile", "create", "test"],
                input="3\n3.0\n\n14\n\n\n\n",
            )
            with patch.object(cli_mod, "api_call") as mock_api:
                mock_api.return_value.__enter__.return_value = fake_api
                result = runner.invoke(app, [
                    "profile", "not-interested", "rm",
                    "test", "Bowron Lake", "2026-07-01", "2026-07-03",
                ])
        assert result.exit_code == 2
        assert "No matching not-interested entry" in result.stderr

    def test_rm_unknown_profile(self, tmp_path):
        db = tmp_path / "state.db"
        from campcli.composition import cli as cli_mod
        from unittest.mock import patch

        with patch.object(cli_mod, "DB_PATH", db):
            result = runner.invoke(app, [
                "profile", "not-interested", "rm",
                "nonexistent", "Bowron Lake", "2026-07-01", "2026-07-03",
            ])
        assert result.exit_code == 2
        assert "not found" in result.stderr

    def test_rm_unknown_park(self, tmp_path, fake_api):
        db = tmp_path / "state.db"
        from campcli.composition import cli as cli_mod
        from unittest.mock import patch

        with patch.object(cli_mod, "DB_PATH", db):
            runner.invoke(
                app, ["profile", "create", "test"],
                input="3\n3.0\n\n14\n\n\n\n",
            )
            with patch.object(cli_mod, "api_call") as mock_api:
                mock_api.return_value.__enter__.return_value = fake_api
                result = runner.invoke(app, [
                    "profile", "not-interested", "rm",
                    "test", "NoSuchPark", "2026-07-01", "2026-07-03",
                ])
        assert result.exit_code == 2
        assert "no park matches" in result.stderr

    def test_list_with_entries(self, tmp_path, fake_api):
        db = tmp_path / "state.db"
        from campcli.composition import cli as cli_mod
        from unittest.mock import patch

        with patch.object(cli_mod, "DB_PATH", db):
            runner.invoke(
                app, ["profile", "create", "test"],
                input="3\n3.0\n\n14\n\n\n\n",
            )
            with patch.object(cli_mod, "api_call") as mock_api:
                mock_api.return_value.__enter__.return_value = fake_api
                runner.invoke(app, [
                    "profile", "not-interested", "add",
                    "test", "Bowron Lake", "2026-07-01", "2026-07-03",
                ])
            with patch.object(cli_mod, "api_call") as mock_api:
                mock_api.return_value.__enter__.return_value = fake_api
                result = runner.invoke(app, [
                    "profile", "not-interested", "list", "test",
                ])
        assert result.exit_code == 0
        assert "Bowron Lake" in result.stdout
        assert "2026-07-01" in result.stdout
        assert "2026-07-03" in result.stdout

    def test_list_empty(self, tmp_path):
        db = tmp_path / "state.db"
        from campcli.composition import cli as cli_mod
        from unittest.mock import patch

        with patch.object(cli_mod, "DB_PATH", db):
            runner.invoke(
                app, ["profile", "create", "test"],
                input="3\n3.0\n\n14\n\n\n\n",
            )
            result = runner.invoke(app, [
                "profile", "not-interested", "list", "test",
            ])
        assert result.exit_code == 0
        assert "No not-interested entries" in result.stdout

    def test_list_unknown_profile(self, tmp_path):
        db = tmp_path / "state.db"
        from campcli.composition import cli as cli_mod
        from unittest.mock import patch

        with patch.object(cli_mod, "DB_PATH", db):
            result = runner.invoke(app, [
                "profile", "not-interested", "list", "nonexistent",
            ])
        assert result.exit_code == 2
        assert "not found" in result.stderr

    def test_e2e_cli_add_skips_in_poll(self, tmp_path, fake_api):
        """End-to-end: CLI add → repo.list_for → SearchNotifier skips match."""
        db = tmp_path / "state.db"
        from datetime import date
        from unittest.mock import patch
        from campcli.composition import cli as cli_mod
        from campcli.infrastructure.store import SqliteStore
        from campcli.application.search_notifier import SearchNotifier
        from campcli.application.drive_times import DriveTimes
        from campcli.domain.models import WeekendMatch

        store = SqliteStore(db)

        # Create profile via CLI
        with patch.object(cli_mod, "DB_PATH", db):
            result = runner.invoke(
                app, ["profile", "create", "e2e"],
                input="3\n3.0\n\n14\nfri-sun\n\nBowron Lake\n\n\n\n",
            )
        assert result.exit_code == 0

        # Add not-interested via CLI
        with patch.object(cli_mod, "DB_PATH", db):
            with patch.object(cli_mod, "api_call") as mock_api:
                mock_api.return_value.__enter__.return_value = fake_api
                result = runner.invoke(app, [
                    "profile", "not-interested", "add",
                    "e2e", "Bowron Lake", "2026-07-01", "2026-07-03",
                ])
        assert result.exit_code == 0

        # Verify via repo
        profile = store.get_by_name("e2e")
        entries = store.list_for(profile.id)
        assert len(entries) == 1
        assert entries[0].park_id == 1
        assert entries[0].date_start == date(2026, 7, 1)
        assert entries[0].date_end == date(2026, 7, 3)

        # Build notifier with same store as not_interested_repo
        class _FakeTelegram:
            def __init__(self):
                self.sent: list[str] = []
            def send_to(self, chat_id: str, text: str) -> int:
                self.sent.append(text)
                return len(self.sent)

        notifier = SearchNotifier(
            telegram=_FakeTelegram(),
            drive_times=DriveTimes.empty(),
            log=lambda msg: None,
            render_match_message=lambda *a, **kw: "",
            not_interested_repo=store,
        )
        notifier.start_poll([], set(), profile_id=profile.id)

        # Match in skip set is silently dropped
        match_skipped = WeekendMatch(
            park_id=1, park_name="Bowron Lake", map_id=10, map_name="Main",
            start_date=date(2026, 7, 1), end_date=date(2026, 7, 3),
            nights=2, available_count=1,
        )
        notifier.notify(match_skipped, chat_ids=["chat1"])
        assert len(notifier._telegram.sent) == 0

        # Match NOT in skip set is sent
        match_sent = WeekendMatch(
            park_id=2, park_name="Golden Ears", map_id=10, map_name="Main",
            start_date=date(2026, 8, 1), end_date=date(2026, 8, 3),
            nights=2, available_count=1,
        )
        notifier.notify(match_sent, chat_ids=["chat1"])
        assert len(notifier._telegram.sent) == 1
