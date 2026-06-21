from campcli.domain.ports import TelegramUpdate


class TestPollerStart:
    def test_start_sends_startup_message(self, poller, fake_telegram):
        poller.start()
        assert "campcli daemon started v3" in " ".join(fake_telegram.sent)


class TestPollerCommands:
    def test_verbose_on(self, poller, fake_telegram, store):
        fake_telegram.canned_updates = [
            TelegramUpdate(update_id=1, chat_id="1", text="/verbose on")
        ]
        poller.tick()
        assert poller._verbose is True
        assert store.get_setting("verbose") == "on"
        assert "verbose logging ON" in fake_telegram.sent

    def test_verbose_off(self, poller, fake_telegram, store):
        store.set_setting("verbose", "on")
        fake_telegram.canned_updates = [
            TelegramUpdate(update_id=1, chat_id="1", text="/verbose off")
        ]
        poller.tick()
        assert poller._verbose is False
        assert store.get_setting("verbose") == "off"
        assert "verbose logging OFF" in fake_telegram.sent

    def test_unknown_command(self, poller, fake_telegram, store):
        fake_telegram.canned_updates = [
            TelegramUpdate(update_id=1, chat_id="1", text="garbage")
        ]
        poller.tick()
        assert poller._verbose is False


class TestPollerNotificationWiring:
    def test_tick_calls_start_poll(self, poller, fake_notifier):
        poller.tick()
        assert len(fake_notifier.start_poll_calls) == 1
