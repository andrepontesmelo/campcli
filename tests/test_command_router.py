from datetime import date

from campcli.application import command_router
from campcli.domain.models import Profile
from campcli.domain.ports import TelegramUpdate
from campcli.infrastructure.store import SqliteStore


class TestDispatch:
    def test_verbose_on(self, command_context):
        upd = TelegramUpdate(update_id=1, chat_id="100", text="/verbose on", from_id=1)
        result = command_router.dispatch(upd, command_context, [1])
        assert result is not None
        assert result["type"] == "reply"
        assert result["text"] == "verbose logging ON"

    def test_verbose_off(self, command_context):
        upd = TelegramUpdate(update_id=1, chat_id="100", text="/verbose off", from_id=1)
        result = command_router.dispatch(upd, command_context, [1])
        assert result is not None
        assert result["type"] == "reply"
        assert result["text"] == "verbose logging OFF"

    def test_unknown_command_returns_none(self, command_context):
        upd = TelegramUpdate(update_id=1, chat_id="100", text="garbage", from_id=1)
        result = command_router.dispatch(upd, command_context, [1])
        assert result is None

    def test_whitespace_around_command(self, command_context):
        upd = TelegramUpdate(update_id=1, chat_id="100", text="  /verbose on  ", from_id=1)
        result = command_router.dispatch(upd, command_context, [1])
        assert result is not None
        assert result["type"] == "reply"
        assert result["text"] == "verbose logging ON"

    def test_bare_verbose_returns_inline_keyboard(self, command_context):
        upd = TelegramUpdate(update_id=1, chat_id="100", text="/verbose", from_id=1)
        result = command_router.dispatch(upd, command_context, [1])
        assert result is not None
        assert result["type"] == "inline_keyboard"
        assert "verbose logging" in result["text"]
        assert "buttons" in result

    def test_unauthorized_user(self, command_context):
        upd = TelegramUpdate(update_id=1, chat_id="100", text="/verbose", from_id=999)
        result = command_router.dispatch(upd, command_context, [1])
        assert result is not None
        assert result["type"] == "reply"
        assert "Your Telegram ID is 999" in result["text"]

    def test_callback_verbose_on(self, command_context):
        upd = TelegramUpdate(
            update_id=2, chat_id="100", text="",
            from_id=1, callback_query_id="cb1", callback_data="verbose_on",
        )
        result = command_router.dispatch(upd, command_context, [1])
        assert result is not None
        assert result["type"] == "callback"
        assert "ON" in result["text"]

    # ---- /not-interested --------------------------------------------------

    def test_not_interested_standalone_shows_guidance(self, command_context):
        upd = TelegramUpdate(
            update_id=3, chat_id="100", text="/not-interested", from_id=1,
        )
        result = command_router.dispatch(upd, command_context, [1])
        assert result is not None
        assert result["type"] == "reply"
        assert "Reply this command" in result["text"]

    def test_not_interested_unknown_message_id(self, command_context):
        upd = TelegramUpdate(
            update_id=3, chat_id="100", text="/not-interested",
            from_id=1, reply_to_message_id=999,
        )
        result = command_router.dispatch(upd, command_context, [1])
        assert result is not None
        assert result["type"] == "reply"
        assert "Could not find" in result["text"]

    def test_not_interested_unauthorized_user(self, store, command_context):
        profile = store.create(Profile(name="test", tg_allowed_ids=[2]))
        store.add_tg_id("test", 2)
        store.record_sent(
            message_id=42, profile_id=profile.id,
            park_id=1, date_start=date(2026, 7, 3), date_end=date(2026, 7, 5),
        )
        command_context.profile_repo = store
        upd = TelegramUpdate(
            update_id=3, chat_id="100", text="/not-interested",
            from_id=1, reply_to_message_id=42,
        )
        result = command_router.dispatch(upd, command_context, [1])
        assert result is not None
        assert result["type"] == "reply"
        assert "Not authorized" in result["text"]

    def test_not_interested_already_marked(self, store, command_context):
        profile = store.create(Profile(name="test2", tg_allowed_ids=[1]))
        store.add_tg_id("test2", 1)
        store.record_sent(
            message_id=43, profile_id=profile.id,
            park_id=2, date_start=date(2026, 7, 10), date_end=date(2026, 7, 12),
        )
        store.add(
            profile_id=profile.id, park_id=2,
            date_start=date(2026, 7, 10), date_end=date(2026, 7, 12),
        )
        command_context.profile_repo = store
        upd = TelegramUpdate(
            update_id=3, chat_id="100", text="/not-interested",
            from_id=1, reply_to_message_id=43,
        )
        result = command_router.dispatch(upd, command_context, [1])
        assert result is not None
        assert result["type"] == "reply"
        assert "Already marked" in result["text"]

    def test_not_interested_happy_path(self, store, command_context):
        profile = store.create(Profile(name="test3", tg_allowed_ids=[1]))
        store.add_tg_id("test3", 1)
        store.record_sent(
            message_id=44, profile_id=profile.id,
            park_id=1, date_start=date(2026, 7, 3), date_end=date(2026, 7, 5),
        )
        command_context.profile_repo = store
        upd = TelegramUpdate(
            update_id=3, chat_id="100", text="/not-interested",
            from_id=1, reply_to_message_id=44,
        )
        result = command_router.dispatch(upd, command_context, [1])
        assert result is not None
        assert result["type"] == "reply"
        assert "NotInterested recorded" in result["text"]
        assert "Bowron Lake" in result["text"]
        assert "2026-07-03" in result["text"]
