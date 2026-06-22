"""Tests for telegram_users module: auth, unauthorized reply, verbose chat set."""
from campcli.application import telegram_users


class TestIsAuthorized:
    def test_authorized_user(self):
        assert telegram_users.is_authorized(12345, [12345, 67890]) is True

    def test_unauthorized_user(self):
        assert telegram_users.is_authorized(99999, [12345]) is False

    def test_empty_list_means_no_one_authorized(self):
        assert telegram_users.is_authorized(12345, []) is False


class TestUnauthorizedReply:
    def test_reply_contains_id_and_instruction(self):
        reply = telegram_users.unauthorized_reply(99999)
        assert "99999" in reply
        assert "campcli telegram allow" in reply


class TestBuildVerboseChatSet:
    def test_builds_set_from_settings(self, store):
        store.set_setting("verbose:1", "on")
        store.set_setting("chat:1", "chat_a")
        store.set_setting("verbose:2", "off")
        store.set_setting("chat:2", "chat_b")
        store.set_setting("verbose:3", "on")
        # No chat:3 set → should be skipped
        chats = telegram_users.build_verbose_chat_set(store, [1, 2, 3])
        assert chats == {"chat_a"}

    def test_no_verbose_on_returns_empty(self, store):
        store.set_setting("verbose:1", "off")
        store.set_setting("chat:1", "chat_a")
        chats = telegram_users.build_verbose_chat_set(store, [1])
        assert chats == set()

    def test_empty_allowed_ids_returns_empty(self, store):
        chats = telegram_users.build_verbose_chat_set(store, [])
        assert chats == set()
