"""Tests for daemon startup and command processing (Poller-less).

Replaces the old Poller-based tests with CommandContext-based wiring.
"""
from __future__ import annotations

from campcli.application import telegram_settings
from campcli.application.command_responses import handle_one_command_batch
from campcli.application.daemon_log import INFO
from campcli.composition.daemon import startup
from campcli.domain.ports import TelegramUpdate


def _noop_log(*_a, **_kw):
    pass


class TestDaemonStartup:
    """Startup logic extracted from the dissolved Poller class."""

    def test_startup_sends_startup_message(self, fake_telegram, store):
        store.set_setting("chat:1", "100")
        startup(
            telegram=fake_telegram,
            tg_allowed_ids=[1],
            settings_repo=store,
            log=_noop_log,
        )
        assert "campcli daemon started v3" in " ".join(fake_telegram.sent)

    def test_startup_registers_commands(self, fake_telegram, store):
        startup(
            telegram=fake_telegram,
            tg_allowed_ids=[],
            settings_repo=store,
            log=_noop_log,
        )
        assert fake_telegram.commands_registered is not None


class TestCommandBatchProcessing:
    """Command processing via handle_one_command_batch."""

    def test_verbose_on(self, command_context, fake_telegram, store):
        fake_telegram.canned_updates = [
            TelegramUpdate(update_id=1, chat_id="100", text="/verbose on", from_id=1)
        ]
        handle_one_command_batch(
            ctx=command_context,
            telegram=fake_telegram,
            tg_allowed_ids=[1],
            log=_noop_log,
            refresh_verbose_chats=lambda: None,
            settings_repo=store,
        )
        assert store.get_setting("verbose:1") == "on"
        assert "verbose logging ON" in fake_telegram.sent

    def test_verbose_off(self, command_context, fake_telegram, store):
        store.set_setting("verbose:1", "on")
        fake_telegram.canned_updates = [
            TelegramUpdate(update_id=1, chat_id="100", text="/verbose off", from_id=1)
        ]
        handle_one_command_batch(
            ctx=command_context,
            telegram=fake_telegram,
            tg_allowed_ids=[1],
            log=_noop_log,
            refresh_verbose_chats=lambda: None,
            settings_repo=store,
        )
        assert store.get_setting("verbose:1") == "off"
        assert "verbose logging OFF" in fake_telegram.sent

    def test_unknown_command(self, command_context, fake_telegram, store):
        fake_telegram.canned_updates = [
            TelegramUpdate(update_id=1, chat_id="100", text="garbage", from_id=1)
        ]
        handle_one_command_batch(
            ctx=command_context,
            telegram=fake_telegram,
            tg_allowed_ids=[1],
            log=_noop_log,
            refresh_verbose_chats=lambda: None,
            settings_repo=store,
        )
        assert telegram_settings.get_verbose(store, 1) is False


class TestNotificationWiring:
    """Separation of concerns: command processing does not trigger search."""

    def test_handle_one_command_batch_no_updates(
        self, command_context, fake_telegram, store
    ):
        """handle_one_command_batch with no updates returns None."""
        result = handle_one_command_batch(
            ctx=command_context,
            telegram=fake_telegram,
            tg_allowed_ids=[],
            log=_noop_log,
            refresh_verbose_chats=lambda: None,
            settings_repo=store,
        )
        assert result is None

    def test_unauthorized_user_receives_id_message(
        self, command_context, fake_telegram, store
    ):
        fake_telegram.canned_updates = [
            TelegramUpdate(update_id=1, chat_id="100", text="/verbose", from_id=999)
        ]
        handle_one_command_batch(
            ctx=command_context,
            telegram=fake_telegram,
            tg_allowed_ids=[1],
            log=_noop_log,
            refresh_verbose_chats=lambda: None,
            settings_repo=store,
        )
        assert "Your Telegram ID is 999" in " ".join(fake_telegram.sent)

    def test_empty_tg_allowed_ids_no_commands(
        self, command_context, fake_telegram, store
    ):
        """When tg_allowed_ids is empty, no one is authorized, no commands processed."""
        fake_telegram.canned_updates = [
            TelegramUpdate(update_id=1, chat_id="100", text="/verbose on", from_id=1)
        ]
        handle_one_command_batch(
            ctx=command_context,
            telegram=fake_telegram,
            tg_allowed_ids=[],
            log=_noop_log,
            refresh_verbose_chats=lambda: None,
            settings_repo=store,
        )
        # No verbose state set
        assert store.get_setting("verbose:1") is None
        # Bot sends ID-revealing message to unauthorized user
        assert len(fake_telegram.sent) >= 1
        assert "Your Telegram ID is" in fake_telegram.sent[0]

    def test_last_seen_chat_tracking(
        self, command_context, fake_telegram, store
    ):
        fake_telegram.canned_updates = [
            TelegramUpdate(update_id=1, chat_id="200", text="/verbose on", from_id=1)
        ]
        handle_one_command_batch(
            ctx=command_context,
            telegram=fake_telegram,
            tg_allowed_ids=[1],
            log=_noop_log,
            refresh_verbose_chats=lambda: None,
            settings_repo=store,
        )
        assert store.get_setting("chat:1") == "200"

    def test_unauthorized_callback_query_answered(
        self, command_context, fake_telegram, store
    ):
        """Unauthorized callback query must answer (dismiss spinner)."""
        fake_telegram.canned_updates = [
            TelegramUpdate(
                update_id=1, chat_id="100", text="",
                from_id=999, callback_query_id="cb_unauth",
                callback_data="verbose_on",
            )
        ]
        handle_one_command_batch(
            ctx=command_context,
            telegram=fake_telegram,
            tg_allowed_ids=[1],
            log=_noop_log,
            refresh_verbose_chats=lambda: None,
            settings_repo=store,
        )
        # The unanswered callback query would leave the spinner spinning;
        # the fix requires answer_callback_query to be called.
        assert "cb_unauth" in fake_telegram.answered_callbacks
