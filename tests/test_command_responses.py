"""Tests for command_responses module.

Unit tests for process_update, handle_commands_forever, and
handle_one_command_batch using fake Telegram adapter and fake Poller.
"""
from __future__ import annotations

from campcli.application import telegram_settings
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


class FakePoller:
    """Minimal Poller duck-type supporting command_router.dispatch needs."""

    def __init__(
        self,
        telegram: FakeTelegram,
        settings_repo: FakeSettingsRepo,
        *,
        tg_allowed_ids: list[int] | None = None,
    ) -> None:
        self._telegram = telegram
        self._settings_repo = settings_repo
        self._tg_allowed_ids = tg_allowed_ids or []
        # Command router dispatch accesses these for /not-interested
        self._not_interested_repo = None
        self._profile_repo = None
        self._api = None
        self.logged: list[str] = []
        self.verbose_chats_refreshed = False

    def _get_verbose(self, tg_id: int) -> bool:
        return telegram_settings.get_verbose(self._settings_repo, tg_id)

    def set_verbose(
        self, tg_id: int, on: bool, chat_id: str | None = None
    ) -> None:
        telegram_settings.set_verbose(self._settings_repo, tg_id, on)

    def log(self, msg: str, level: int = INFO) -> None:
        self.logged.append(msg)

    def _refresh_verbose_chats(self) -> None:
        self.verbose_chats_refreshed = True


# =========================================================================
# process_update
# =========================================================================


class TestProcessUpdate:
    """Direct unit tests for process_update()."""

    def test_unknown_command_returns_offset(self) -> None:
        """Unknown text → dispatch returns None → no reply, correct offset."""
        tg = FakeTelegram()
        sr = FakeSettingsRepo()
        poller = FakePoller(tg, sr, tg_allowed_ids=[1])
        upd = TelegramUpdate(
            update_id=1, chat_id="100", text="garbage", from_id=1
        )

        result = process_update(
            upd,
            poller=poller,
            telegram=tg,
            settings_repo=sr,
            tg_allowed_ids=[1],
            log=poller.log,
            refresh_verbose_chats=poller._refresh_verbose_chats,
        )

        assert result == 2  # update_id + 1
        assert tg.sent == []

    def test_verbose_on_sends_reply(self) -> None:
        """/verbose on → reply type → text sent via telegram.send_to."""
        tg = FakeTelegram()
        sr = FakeSettingsRepo()
        poller = FakePoller(tg, sr, tg_allowed_ids=[1])
        upd = TelegramUpdate(
            update_id=5, chat_id="100", text="/verbose on", from_id=1
        )

        result = process_update(
            upd,
            poller=poller,
            telegram=tg,
            settings_repo=sr,
            tg_allowed_ids=[1],
            log=poller.log,
            refresh_verbose_chats=poller._refresh_verbose_chats,
        )

        assert result == 6
        assert "verbose logging ON" in tg.sent[0]
        assert sr.get_setting("verbose:1") == "on"

    def test_verbose_off_sends_reply(self) -> None:
        """/verbose off → reply type → text sent."""
        tg = FakeTelegram()
        sr = FakeSettingsRepo()
        sr.set_setting("verbose:1", "on")
        poller = FakePoller(tg, sr, tg_allowed_ids=[1])
        upd = TelegramUpdate(
            update_id=3, chat_id="100", text="/verbose off", from_id=1
        )

        result = process_update(
            upd,
            poller=poller,
            telegram=tg,
            settings_repo=sr,
            tg_allowed_ids=[1],
            log=poller.log,
            refresh_verbose_chats=poller._refresh_verbose_chats,
        )

        assert result == 4
        assert "verbose logging OFF" in tg.sent[0]
        assert sr.get_setting("verbose:1") == "off"

    def test_verbose_bare_sends_inline_keyboard(self) -> None:
        """/verbose → inline_keyboard type → keyboard sent."""
        tg = FakeTelegram()
        sr = FakeSettingsRepo()
        poller = FakePoller(tg, sr, tg_allowed_ids=[1])
        upd = TelegramUpdate(
            update_id=10, chat_id="100", text="/verbose", from_id=1
        )

        result = process_update(
            upd,
            poller=poller,
            telegram=tg,
            settings_repo=sr,
            tg_allowed_ids=[1],
            log=poller.log,
            refresh_verbose_chats=poller._refresh_verbose_chats,
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
        """Callback → answer_callback_query + edit_message_reply_markup."""
        tg = FakeTelegram()
        sr = FakeSettingsRepo()
        sr.set_setting("verbose:1", "off")
        poller = FakePoller(tg, sr, tg_allowed_ids=[1])
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
            poller=poller,
            telegram=tg,
            settings_repo=sr,
            tg_allowed_ids=[1],
            log=poller.log,
            refresh_verbose_chats=poller._refresh_verbose_chats,
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
        """Callback → answer_callback_query + edit_message_reply_markup."""
        tg = FakeTelegram()
        sr = FakeSettingsRepo()
        sr.set_setting("verbose:1", "on")
        poller = FakePoller(tg, sr, tg_allowed_ids=[1])
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
            poller=poller,
            telegram=tg,
            settings_repo=sr,
            tg_allowed_ids=[1],
            log=poller.log,
            refresh_verbose_chats=poller._refresh_verbose_chats,
        )

        assert result == 9
        assert "cb_2" in tg.answered_callbacks
        assert len(tg.edited_messages) == 1
        assert "OFF" in tg.edited_messages[0][2]
        assert sr.get_setting("verbose:1") == "off"

    def test_unauthorized_user_gets_id_message(self) -> None:
        """Unauthorized → reply with 'Your Telegram ID is ...'."""
        tg = FakeTelegram()
        sr = FakeSettingsRepo()
        poller = FakePoller(tg, sr, tg_allowed_ids=[1])
        upd = TelegramUpdate(
            update_id=2, chat_id="100", text="/verbose", from_id=999
        )

        result = process_update(
            upd,
            poller=poller,
            telegram=tg,
            settings_repo=sr,
            tg_allowed_ids=[1],
            log=poller.log,
            refresh_verbose_chats=poller._refresh_verbose_chats,
        )

        assert result == 3
        assert len(tg.sent) == 1
        assert "Your Telegram ID is 999" in tg.sent[0]

    def test_chat_tracking_updates_chat_id(self) -> None:
        """Authorized user from new chat → chat_id updated in settings."""
        tg = FakeTelegram()
        sr = FakeSettingsRepo()
        sr.set_setting("chat:1", "100")
        poller = FakePoller(tg, sr, tg_allowed_ids=[1])
        upd = TelegramUpdate(
            update_id=4, chat_id="200", text="/verbose on", from_id=1
        )

        process_update(
            upd,
            poller=poller,
            telegram=tg,
            settings_repo=sr,
            tg_allowed_ids=[1],
            log=poller.log,
            refresh_verbose_chats=poller._refresh_verbose_chats,
        )

        assert sr.get_setting("chat:1") == "200"

    def test_callback_query_with_unknown_callback_data(self) -> None:
        """Unknown callback data → dispatch returns reply → callback answered
        + reply sent."""
        tg = FakeTelegram()
        sr = FakeSettingsRepo()
        poller = FakePoller(tg, sr, tg_allowed_ids=[1])
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
            poller=poller,
            telegram=tg,
            settings_repo=sr,
            tg_allowed_ids=[1],
            log=poller.log,
            refresh_verbose_chats=poller._refresh_verbose_chats,
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
        poller = FakePoller(tg, sr, tg_allowed_ids=[1])
        tg.canned_updates = [
            TelegramUpdate(
                update_id=1, chat_id="100", text="/verbose on", from_id=1
            ),
            TelegramUpdate(
                update_id=2, chat_id="100", text="/verbose off", from_id=1
            ),
        ]

        last_offset = handle_one_command_batch(poller)

        assert last_offset == 3  # last update_id + 1
        assert len(tg.sent) == 2
        assert "verbose logging ON" in tg.sent[0]
        assert "verbose logging OFF" in tg.sent[1]
        assert sr.get_setting("verbose:1") == "off"

    def test_empty_updates_returns_none(self) -> None:
        """No canned updates → returns None."""
        tg = FakeTelegram()
        sr = FakeSettingsRepo()
        poller = FakePoller(tg, sr, tg_allowed_ids=[1])

        result = handle_one_command_batch(poller)

        assert result is None

    def test_explicit_kwargs_override_poller(self) -> None:
        """Explicit telegram/settings_repo override Poller attributes."""
        tg1 = FakeTelegram()
        tg2 = FakeTelegram()
        sr = FakeSettingsRepo()
        poller = FakePoller(tg1, sr, tg_allowed_ids=[1])
        # Set canned on tg2, not tg1
        tg2.canned_updates = [
            TelegramUpdate(
                update_id=5, chat_id="100", text="/verbose on", from_id=1
            ),
        ]

        last_offset = handle_one_command_batch(
            poller,
            telegram=tg2,
            settings_repo=sr,
            tg_allowed_ids=[1],
            log=poller.log,
            refresh_verbose_chats=poller._refresh_verbose_chats,
            update_offset=None,
        )

        assert last_offset == 6
        assert len(tg2.sent) == 1
        assert tg1.sent == []  # tg1 not used

    def test_unauthorized_in_batch(self) -> None:
        """Batch with unauthorized user still processes."""
        tg = FakeTelegram()
        sr = FakeSettingsRepo()
        poller = FakePoller(tg, sr, tg_allowed_ids=[1])
        tg.canned_updates = [
            TelegramUpdate(
                update_id=1, chat_id="100", text="/verbose", from_id=999
            ),
            TelegramUpdate(
                update_id=2, chat_id="100", text="/verbose on", from_id=1
            ),
        ]

        handle_one_command_batch(poller)

        # First: unauthorized reply
        assert "Your Telegram ID is 999" in tg.sent[0]
        # Second: verbose on
        assert "verbose logging ON" in tg.sent[1]
        assert sr.get_setting("verbose:1") == "on"
