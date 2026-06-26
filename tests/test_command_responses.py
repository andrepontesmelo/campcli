"""Tests for command_responses module.

Unit tests for process_update, handle_commands_forever, and
handle_one_command_batch using fake Telegram adapter and CommandContext.
"""
from __future__ import annotations

from campcli.application import telegram_settings
from campcli.application.command_router import CommandContext
from campcli.application.command_responses import (
    handle_one_command_batch,
    process_update,
)
from campcli.application.daemon_log import INFO
from campcli.domain.ports import TelegramUpdate
from conftest import FakeTelegram


class FakeSettingsRepo:
    """In-memory SettingsRepo for testing."""

    def __init__(self) -> None:
        self._data: dict[str, str] = {}

    def get_setting(self, key: str) -> str | None:
        return self._data.get(key)

    def set_setting(self, key: str, value: str) -> None:
        self._data[key] = value


def _build_ctx(sr: FakeSettingsRepo) -> CommandContext:
    """Build a minimal CommandContext for command-responses tests."""
    return CommandContext(
        api=None,
        settings_repo=sr,
        profile_repo=None,
        not_interested_repo=None,
        _refresh_verbose_chats=lambda: None,
    )


def _noop_log(*_a, **_kw):
    pass


# =========================================================================
# process_update
# =========================================================================


class TestProcessUpdate:
    """Direct unit tests for process_update()."""

    def test_unknown_command_returns_offset(self) -> None:
        """Unknown text â†' dispatch returns None â†' no reply, correct offset."""
        tg = FakeTelegram()
        sr = FakeSettingsRepo()
        ctx = _build_ctx(sr)
        upd = TelegramUpdate(
            update_id=1, chat_id="100", text="garbage", from_id=1
        )

        result = process_update(
            upd,
            ctx=ctx,
            telegram=tg,
            settings_repo=sr,
            tg_allowed_ids=[1],
            log=_noop_log,
            refresh_verbose_chats=_noop_log,
        )

        assert result == 2  # update_id + 1
        assert tg.sent == []

    def test_verbose_on_sends_reply(self) -> None:
        """/verbose on â†' reply type â†' text sent via telegram.send_to."""
        tg = FakeTelegram()
        sr = FakeSettingsRepo()
        ctx = _build_ctx(sr)
        upd = TelegramUpdate(
            update_id=5, chat_id="100", text="/verbose on", from_id=1
        )

        result = process_update(
            upd,
            ctx=ctx,
            telegram=tg,
            settings_repo=sr,
            tg_allowed_ids=[1],
            log=_noop_log,
            refresh_verbose_chats=_noop_log,
        )

        assert result == 6
        assert "verbose logging ON" in tg.sent[0]
        assert sr.get_setting("verbose:1") == "on"

    def test_verbose_off_sends_reply(self) -> None:
        """/verbose off â†' reply type â†' text sent."""
        tg = FakeTelegram()
        sr = FakeSettingsRepo()
        sr.set_setting("verbose:1", "on")
        ctx = _build_ctx(sr)
        upd = TelegramUpdate(
            update_id=3, chat_id="100", text="/verbose off", from_id=1
        )

        result = process_update(
            upd,
            ctx=ctx,
            telegram=tg,
            settings_repo=sr,
            tg_allowed_ids=[1],
            log=_noop_log,
            refresh_verbose_chats=_noop_log,
        )

        assert result == 4
        assert "verbose logging OFF" in tg.sent[0]
        assert sr.get_setting("verbose:1") == "off"

    def test_verbose_bare_sends_inline_keyboard(self) -> None:
        """/verbose â†' inline_keyboard type â†' keyboard sent."""
        tg = FakeTelegram()
        sr = FakeSettingsRepo()
        ctx = _build_ctx(sr)
        upd = TelegramUpdate(
            update_id=10, chat_id="100", text="/verbose", from_id=1
        )

        result = process_update(
            upd,
            ctx=ctx,
            telegram=tg,
            settings_repo=sr,
            tg_allowed_ids=[1],
            log=_noop_log,
            refresh_verbose_chats=_noop_log,
        )

        assert result == 11
        assert len(tg.inline_keyboards_sent) == 1
        chat_id, text, buttons = tg.inline_keyboards_sent[0]
        assert chat_id == "100"
        assert "verbose" in text.lower()
        assert buttons == [
            [
                {"text": "ON", "callback_data": "verbose_on"},
                {"text": "OFF", "callback_data": "verbose_off"},
            ]
        ]

    def test_callback_verbose_on(self) -> None:
        """Callback â†' answer_callback_query + edit_message_reply_markup."""
        tg = FakeTelegram()
        sr = FakeSettingsRepo()
        sr.set_setting("verbose:1", "off")
        ctx = _build_ctx(sr)
        upd = TelegramUpdate(
            update_id=7,
            chat_id="100",
            text="",
            from_id=1,
            callback_query_id="cb_1",
            callback_data="verbose_on",
            message_id=42,
        )

        result = process_update(
            upd,
            ctx=ctx,
            telegram=tg,
            settings_repo=sr,
            tg_allowed_ids=[1],
            log=_noop_log,
            refresh_verbose_chats=_noop_log,
        )

        assert result == 8
        assert "cb_1" in tg.answered_callbacks
        assert len(tg.edited_messages) == 1
        chat_id, msg_id, text, _ = tg.edited_messages[0]
        assert chat_id == "100"
        assert msg_id == 42
        assert "ON" in text
        assert sr.get_setting("verbose:1") == "on"

    def test_callback_verbose_off(self) -> None:
        """Callback â†' answer_callback_query + edit_message_reply_markup."""
        tg = FakeTelegram()
        sr = FakeSettingsRepo()
        sr.set_setting("verbose:1", "on")
        ctx = _build_ctx(sr)
        upd = TelegramUpdate(
            update_id=8,
            chat_id="100",
            text="",
            from_id=1,
            callback_query_id="cb_2",
            callback_data="verbose_off",
            message_id=43,
        )

        result = process_update(
            upd,
            ctx=ctx,
            telegram=tg,
            settings_repo=sr,
            tg_allowed_ids=[1],
            log=_noop_log,
            refresh_verbose_chats=_noop_log,
        )

        assert result == 9
        assert "cb_2" in tg.answered_callbacks
        assert len(tg.edited_messages) == 1
        assert "OFF" in tg.edited_messages[0][2]
        assert sr.get_setting("verbose:1") == "off"

    def test_unauthorized_user_gets_id_message(self) -> None:
        """Unauthorized â†' reply with 'Your Telegram ID is ...'."""
        tg = FakeTelegram()
        sr = FakeSettingsRepo()
        ctx = _build_ctx(sr)
        upd = TelegramUpdate(
            update_id=2, chat_id="100", text="/verbose", from_id=999
        )

        result = process_update(
            upd,
            ctx=ctx,
            telegram=tg,
            settings_repo=sr,
            tg_allowed_ids=[1],
            log=_noop_log,
            refresh_verbose_chats=_noop_log,
        )

        assert result == 3
        assert len(tg.sent) == 1
        assert "Your Telegram ID is 999" in tg.sent[0]

    def test_chat_tracking_updates_chat_id(self) -> None:
        """Authorized user from new chat â†' chat_id updated in settings."""
        tg = FakeTelegram()
        sr = FakeSettingsRepo()
        sr.set_setting("chat:1", "100")
        ctx = _build_ctx(sr)
        upd = TelegramUpdate(
            update_id=4, chat_id="200", text="/verbose on", from_id=1
        )

        process_update(
            upd,
            ctx=ctx,
            telegram=tg,
            settings_repo=sr,
            tg_allowed_ids=[1],
            log=_noop_log,
            refresh_verbose_chats=_noop_log,
        )

        assert sr.get_setting("chat:1") == "200"

    def test_callback_query_with_unknown_callback_data(self) -> None:
        """Unknown callback data â†' dispatch returns reply â†' callback answered
        + reply sent."""
        tg = FakeTelegram()
        sr = FakeSettingsRepo()
        ctx = _build_ctx(sr)
        upd = TelegramUpdate(
            update_id=9,
            chat_id="100",
            text="",
            from_id=1,
            callback_query_id="cb_unknown",
            callback_data="nobody_home",
            message_id=50,
        )

        result = process_update(
            upd,
            ctx=ctx,
            telegram=tg,
            settings_repo=sr,
            tg_allowed_ids=[1],
            log=_noop_log,
            refresh_verbose_chats=_noop_log,
        )

        assert result == 10
        # callback answered (non-callback result still answers)
        assert "cb_unknown" in tg.answered_callbacks
        # reply sent
        assert "unknown command" in tg.sent[0]


# =========================================================================
# handle_one_command_batch
# =========================================================================


class TestHandleOneCommandBatch:
    """Tests for handle_one_command_batch()."""

    def test_processes_all_canned_updates(self) -> None:
        """All canned updates are processed."""
        tg = FakeTelegram()
        sr = FakeSettingsRepo()
        ctx = _build_ctx(sr)
        tg.canned_updates = [
            TelegramUpdate(
                update_id=1, chat_id="100", text="/verbose on", from_id=1
            ),
            TelegramUpdate(
                update_id=2, chat_id="100", text="/verbose off", from_id=1
            ),
        ]

        last_offset = handle_one_command_batch(
            ctx=ctx,
            telegram=tg,
            tg_allowed_ids=[1],
            log=_noop_log,
            refresh_verbose_chats=_noop_log,
            settings_repo=sr,
        )

        assert last_offset == 3  # last update_id + 1
        assert len(tg.sent) == 2
        assert "verbose logging ON" in tg.sent[0]
        assert "verbose logging OFF" in tg.sent[1]
        assert sr.get_setting("verbose:1") == "off"

    def test_empty_updates_returns_none(self) -> None:
        """No canned updates â†' returns None."""
        tg = FakeTelegram()
        sr = FakeSettingsRepo()
        ctx = _build_ctx(sr)

        result = handle_one_command_batch(
            ctx=ctx,
            telegram=tg,
            tg_allowed_ids=[1],
            log=_noop_log,
            refresh_verbose_chats=_noop_log,
            settings_repo=sr,
        )

        assert result is None

    def test_explicit_kwargs_override(self) -> None:
        """Explicit telegram/settings_repo used correctly."""
        tg1 = FakeTelegram()
        tg2 = FakeTelegram()
        sr = FakeSettingsRepo()
        ctx = _build_ctx(sr)
        # Set canned on tg2, not tg1
        tg2.canned_updates = [
            TelegramUpdate(
                update_id=5, chat_id="100", text="/verbose on", from_id=1
            ),
        ]

        last_offset = handle_one_command_batch(
            ctx=ctx,
            telegram=tg2,
            tg_allowed_ids=[1],
            log=_noop_log,
            refresh_verbose_chats=_noop_log,
            settings_repo=sr,
        )

        assert last_offset == 6
        assert len(tg2.sent) == 1
        assert tg1.sent == []  # tg1 not used

    def test_unauthorized_in_batch(self) -> None:
        """Batch with unauthorized user still processes."""
        tg = FakeTelegram()
        sr = FakeSettingsRepo()
        ctx = _build_ctx(sr)
        tg.canned_updates = [
            TelegramUpdate(
                update_id=1, chat_id="100", text="/verbose", from_id=999
            ),
            TelegramUpdate(
                update_id=2, chat_id="100", text="/verbose on", from_id=1
            ),
        ]

        handle_one_command_batch(
            ctx=ctx,
            telegram=tg,
            tg_allowed_ids=[1],
            log=_noop_log,
            refresh_verbose_chats=_noop_log,
            settings_repo=sr,
        )

        # First: unauthorized reply
        assert "Your Telegram ID is 999" in tg.sent[0]
        # Second: verbose on
        assert "verbose logging ON" in tg.sent[1]
        assert sr.get_setting("verbose:1") == "on"
