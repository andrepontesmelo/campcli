"""Tests for HttpxTelegram adapter (multi-user, inline keyboard, etc)."""
from __future__ import annotations

import json

import pytest

from campcli.domain.ports import BotCommand
from campcli.infrastructure.telegram import HttpxTelegram


class TestHttpxTelegramInit:
    def test_no_chat_id_in_init(self):
        tg = HttpxTelegram(token="abc:123")
        assert tg._token == "abc:123"
        tg.close()

    def test_send_to_uses_provided_chat_id(self, httpx_mock):
        httpx_mock.add_response(
            url="https://api.telegram.org/botabc:123/sendMessage",
            method="POST",
            json={"ok": True, "result": {"message_id": 1}},
        )
        tg = HttpxTelegram(token="abc:123")
        tg.send_to("999", "hello")
        req_data = json.loads(httpx_mock.get_request().content)
        assert req_data["chat_id"] == "999"
        tg.close()


class TestHttpxTelegramPollUpdates:
    def test_parses_reply_to_message_id(self, httpx_mock):
        httpx_mock.add_response(
            url="https://api.telegram.org/botabc:123/getUpdates?timeout=0",
            method="GET",
            json={
                "ok": True,
                "result": [
                    {
                        "update_id": 1,
                        "message": {
                            "message_id": 10,
                            "chat": {"id": 100},
                            "from": {"id": 42},
                            "text": "/not-interested",
                            "reply_to_message": {"message_id": 5},
                        },
                    },
                ],
            },
        )
        tg = HttpxTelegram(token="abc:123")
        updates = tg.poll_updates()
        assert len(updates) == 1
        assert updates[0].reply_to_message_id == 5
        tg.close()

    def test_reply_to_message_id_none_when_absent(self, httpx_mock):
        httpx_mock.add_response(
            url="https://api.telegram.org/botabc:123/getUpdates?timeout=0",
            method="GET",
            json={
                "ok": True,
                "result": [
                    {
                        "update_id": 1,
                        "message": {
                            "message_id": 10,
                            "chat": {"id": 100},
                            "from": {"id": 42},
                            "text": "/verbose",
                        },
                    },
                ],
            },
        )
        tg = HttpxTelegram(token="abc:123")
        updates = tg.poll_updates()
        assert len(updates) == 1
        assert updates[0].reply_to_message_id is None
        tg.close()

    def test_returns_all_updates_unfiltered(self, httpx_mock):
        httpx_mock.add_response(
            url="https://api.telegram.org/botabc:123/getUpdates?timeout=0",
            method="GET",
            json={
                "ok": True,
                "result": [
                    {
                        "update_id": 1,
                        "message": {
                            "message_id": 10,
                            "chat": {"id": 100},
                            "from": {"id": 42},
                            "text": "/verbose",
                        },
                    },
                    {
                        "update_id": 2,
                        "message": {
                            "message_id": 11,
                            "chat": {"id": 200},
                            "from": {"id": 99},
                            "text": "hello",
                        },
                    },
                ],
            },
        )
        tg = HttpxTelegram(token="abc:123")
        updates = tg.poll_updates()
        assert len(updates) == 2
        assert updates[0].chat_id == "100"
        assert updates[0].from_id == 42
        assert updates[1].chat_id == "200"
        assert updates[1].from_id == 99
        tg.close()

    def test_handles_callback_query(self, httpx_mock):
        httpx_mock.add_response(
            url="https://api.telegram.org/botabc:123/getUpdates?timeout=0",
            method="GET",
            json={
                "ok": True,
                "result": [
                    {
                        "update_id": 3,
                        "callback_query": {
                            "id": "cb1",
                            "from": {"id": 42},
                            "message": {
                                "message_id": 20,
                                "chat": {"id": 100},
                                "text": "original",
                            },
                            "data": "verbose_on",
                        },
                    },
                ],
            },
        )
        tg = HttpxTelegram(token="abc:123")
        updates = tg.poll_updates()
        assert len(updates) == 1
        assert updates[0].callback_query_id == "cb1"
        assert updates[0].callback_data == "verbose_on"
        assert updates[0].from_id == 42
        assert updates[0].chat_id == "100"
        tg.close()

    def test_poll_updates_error_returns_empty(self, httpx_mock):
        httpx_mock.add_response(
            url="https://api.telegram.org/botabc:123/getUpdates?timeout=0",
            method="GET",
            status_code=500,
        )
        tg = HttpxTelegram(token="abc:123")
        updates = tg.poll_updates()
        assert updates == []
        tg.close()

    def test_poll_updates_ok_false_returns_empty(self, httpx_mock):
        httpx_mock.add_response(
            url="https://api.telegram.org/botabc:123/getUpdates?timeout=0",
            method="GET",
            json={"ok": False},
        )
        tg = HttpxTelegram(token="abc:123")
        updates = tg.poll_updates()
        assert updates == []
        tg.close()


class TestHttpxTelegramCommands:
    def test_set_my_commands(self, httpx_mock):
        httpx_mock.add_response(
            url="https://api.telegram.org/botabc:123/setMyCommands",
            method="POST",
            json={"ok": True},
        )
        tg = HttpxTelegram(token="abc:123")
        tg.set_my_commands([BotCommand(command="verbose", description="Toggle verbose")])
        req_data = json.loads(httpx_mock.get_request().content)
        assert req_data == {
            "commands": [{"command": "verbose", "description": "Toggle verbose"}],
        }
        tg.close()


class TestHttpxTelegramInlineKeyboard:
    def test_send_inline_keyboard_returns_message_id(self, httpx_mock):
        httpx_mock.add_response(
            url="https://api.telegram.org/botabc:123/sendMessage",
            method="POST",
            json={"ok": True, "result": {"message_id": 99}},
        )
        tg = HttpxTelegram(token="abc:123")
        buttons = [[{"text": "ON", "callback_data": "verbose_on"}]]
        mid = tg.send_inline_keyboard("100", "pick one", buttons)
        assert mid == 99
        req_data = json.loads(httpx_mock.get_request().content)
        assert req_data["reply_markup"]["inline_keyboard"] == buttons
        tg.close()

    def test_answer_callback_query(self, httpx_mock):
        httpx_mock.add_response(
            url="https://api.telegram.org/botabc:123/answerCallbackQuery",
            method="POST",
            json={"ok": True},
        )
        tg = HttpxTelegram(token="abc:123")
        tg.answer_callback_query("cb1")
        req_data = json.loads(httpx_mock.get_request().content)
        assert req_data["callback_query_id"] == "cb1"
        tg.close()


class TestHttpxTelegramChunking:
    def test_long_message_chunked(self, httpx_mock):
        httpx_mock.add_response(
            url="https://api.telegram.org/botabc:123/sendMessage",
            method="POST",
            json={"ok": True, "result": {"message_id": 1}},
        )
        httpx_mock.add_response(
            url="https://api.telegram.org/botabc:123/sendMessage",
            method="POST",
            json={"ok": True, "result": {"message_id": 2}},
        )
        tg = HttpxTelegram(token="abc:123")
        long_text = "x" * 5000
        tg.send_to("100", long_text)
        assert len(httpx_mock.get_requests()) == 2
        tg.close()
