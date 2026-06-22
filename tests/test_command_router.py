from campcli.application import command_router
from campcli.domain.ports import TelegramUpdate


class TestDispatch:
    def test_verbose_on(self, poller):
        upd = TelegramUpdate(update_id=1, chat_id="100", text="/verbose on", from_id=1)
        result = command_router.dispatch(upd, poller, [1])
        assert result is not None
        assert result["type"] == "reply"
        assert result["text"] == "verbose logging ON"

    def test_verbose_off(self, poller):
        upd = TelegramUpdate(update_id=1, chat_id="100", text="/verbose off", from_id=1)
        result = command_router.dispatch(upd, poller, [1])
        assert result is not None
        assert result["type"] == "reply"
        assert result["text"] == "verbose logging OFF"

    def test_unknown_command_returns_none(self, poller):
        upd = TelegramUpdate(update_id=1, chat_id="100", text="garbage", from_id=1)
        result = command_router.dispatch(upd, poller, [1])
        assert result is None

    def test_whitespace_around_command(self, poller):
        upd = TelegramUpdate(update_id=1, chat_id="100", text="  /verbose on  ", from_id=1)
        result = command_router.dispatch(upd, poller, [1])
        assert result is not None
        assert result["type"] == "reply"
        assert result["text"] == "verbose logging ON"

    def test_bare_verbose_returns_inline_keyboard(self, poller):
        upd = TelegramUpdate(update_id=1, chat_id="100", text="/verbose", from_id=1)
        result = command_router.dispatch(upd, poller, [1])
        assert result is not None
        assert result["type"] == "inline_keyboard"
        assert "verbose logging" in result["text"]
        assert "buttons" in result

    def test_unauthorized_user(self, poller):
        upd = TelegramUpdate(update_id=1, chat_id="100", text="/verbose", from_id=999)
        result = command_router.dispatch(upd, poller, [1])
        assert result is not None
        assert result["type"] == "reply"
        assert "Your Telegram ID is 999" in result["text"]

    def test_callback_verbose_on(self, poller):
        upd = TelegramUpdate(
            update_id=2, chat_id="100", text="",
            from_id=1, callback_query_id="cb1", callback_data="verbose_on",
        )
        result = command_router.dispatch(upd, poller, [1])
        assert result is not None
        assert result["type"] == "callback"
        assert "ON" in result["text"]
