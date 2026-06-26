from __future__ import annotations

from campcli.domain.ports import TelegramUpdate
from campcli.application.poller import handle_one_command_batch


class TestPollerStart:
    def test_start_sends_startup_message(self, poller, fake_telegram):
        # Without any authorized users, no startup message is sent
        poller._tg_allowed_ids = [1]
        poller._settings_repo.set_setting("chat:1", "100")
        poller.start()
        assert "campcli daemon started v3" in " ".join(fake_telegram.sent)

    def test_start_registers_commands(self, poller, fake_telegram):
        poller.start()
        assert fake_telegram.commands_registered is not None


class TestPollerCommands:
    def test_verbose_on(self, poller, fake_telegram, store):
        poller._tg_allowed_ids = [1]
        fake_telegram.canned_updates = [
            TelegramUpdate(update_id=1, chat_id="100", text="/verbose on", from_id=1)
        ]
        handle_one_command_batch(poller)
        assert store.get_setting("verbose:1") == "on"
        assert "verbose logging ON" in fake_telegram.sent

    def test_verbose_off(self, poller, fake_telegram, store):
        poller._tg_allowed_ids = [1]
        store.set_setting("verbose:1", "on")
        fake_telegram.canned_updates = [
            TelegramUpdate(update_id=1, chat_id="100", text="/verbose off", from_id=1)
        ]
        handle_one_command_batch(poller)
        assert store.get_setting("verbose:1") == "off"
        assert "verbose logging OFF" in fake_telegram.sent

    def test_unknown_command(self, poller, fake_telegram, store):
        fake_telegram.canned_updates = [
            TelegramUpdate(update_id=1, chat_id="100", text="garbage", from_id=1)
        ]
        handle_one_command_batch(poller)
        assert poller._get_verbose(1) is False


class TestPollerNotificationWiring:
    def test_handle_one_command_batch_no_start_poll(self, poller, fake_notifier):
        handle_one_command_batch(poller)
        # handle_one_command_batch only processes Telegram commands;
        # run_search_once (which handles start_poll per profile) is a
        # separate step. If no profiles are enabled, start_poll is never
        # called regardless.
        assert len(fake_notifier.start_poll_calls) == 0

    def test_unauthorized_user_receives_id_message(self, poller, fake_telegram):
        poller._tg_allowed_ids = [1]
        fake_telegram.canned_updates = [
            TelegramUpdate(update_id=1, chat_id="100", text="/verbose", from_id=999)
        ]
        handle_one_command_batch(poller)
        assert "Your Telegram ID is 999" in " ".join(fake_telegram.sent)

    def test_empty_tg_allowed_ids_no_broadcast_no_commands(self, poller, fake_telegram, store):
        """When tg_allowed_ids is empty, no one is authorized, no commands processed."""
        poller._tg_allowed_ids = []
        # Even an authorized-looking user gets rejected
        fake_telegram.canned_updates = [
            TelegramUpdate(update_id=1, chat_id="100", text="/verbose on", from_id=1)
        ]
        handle_one_command_batch(poller)
        # No verbose state set
        assert store.get_setting("verbose:1") is None
        # Bot sends ID-revealing message to unauthorized user
        assert len(fake_telegram.sent) >= 1
        assert "Your Telegram ID is" in fake_telegram.sent[0]

    def test_last_seen_chat_tracking(self, poller, store, fake_telegram):
        poller._tg_allowed_ids = [1]
        fake_telegram.canned_updates = [
            TelegramUpdate(update_id=1, chat_id="200", text="/verbose on", from_id=1)
        ]
        handle_one_command_batch(poller)
        assert store.get_setting("chat:1") == "200"

    def test_unauthorized_callback_query_answered(self, poller, fake_telegram):
        """Unauthorized callback query must answer (dismiss spinner)."""
        poller._tg_allowed_ids = [1]
        fake_telegram.canned_updates = [
            TelegramUpdate(
                update_id=1, chat_id="100", text="",
                from_id=999, callback_query_id="cb_unauth",
                callback_data="verbose_on",
            )
        ]
        handle_one_command_batch(poller)
        # The unanswered callback query would leave the spinner spinning;
        # the fix requires answer_callback_query to be called.
        assert "cb_unauth" in fake_telegram.answered_callbacks
