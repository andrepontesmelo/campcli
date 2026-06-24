"""Tests for DaemonLog — verbose-gated Telegram mirroring."""
from datetime import datetime

from campcli.application.daemon_log import DaemonLog


class FakeTelegram:
    def __init__(self):
        self.sent = []

    def send_to(self, chat_id, text):
        self.sent.append((chat_id, text))
        return 42


class FrozenClock:
    def now(self):
        return datetime(2026, 8, 15, 9, 0, 0)


def test_quiet_does_not_mirror_to_telegram():
    tg = FakeTelegram()
    log = DaemonLog(FrozenClock(), tg)
    log.log("scanning")
    assert tg.sent == []


def test_verbose_mirrors_to_telegram():
    tg = FakeTelegram()
    log = DaemonLog(FrozenClock(), tg, verbose_chats={"chat1"})
    log.log("scanning")
    assert len(tg.sent) == 1
    assert tg.sent[0][0] == "chat1"
    assert "[2026-08-15T09:00:00] scanning" in tg.sent[0][1]


def test_set_verbose_adds_chat():
    tg = FakeTelegram()
    log = DaemonLog(FrozenClock(), tg)
    log.set_verbose("chat1", True)
    log.log("x")
    assert len(tg.sent) == 1
    assert tg.sent[0][0] == "chat1"


def test_set_verbose_removes_chat():
    tg = FakeTelegram()
    log = DaemonLog(FrozenClock(), tg, verbose_chats={"chat1"})
    log.set_verbose("chat1", False)
    log.log("x")
    assert tg.sent == []


def test_multiple_verbose_chats():
    tg = FakeTelegram()
    log = DaemonLog(FrozenClock(), tg, verbose_chats={"chat1", "chat2"})
    log.log("hello")
    assert len(tg.sent) == 2


def test_telegram_failure_is_swallowed():
    class Boom(FakeTelegram):
        def send_to(self, chat_id, text):
            raise RuntimeError("down")

    log = DaemonLog(FrozenClock(), Boom(), verbose_chats={"chat1"})
    log.log("still logs to stderr")  # must not raise
