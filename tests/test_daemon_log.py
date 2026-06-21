"""Tests for DaemonLog — verbose-gated Telegram mirroring."""
from datetime import datetime

from campcli.application.daemon_log import DaemonLog


class FakeTelegram:
    def __init__(self):
        self.sent = []

    def send(self, text):
        self.sent.append(text)


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
    log = DaemonLog(FrozenClock(), tg, verbose=True)
    log.log("scanning")
    assert len(tg.sent) == 1 and "scanning" in tg.sent[0]


def test_set_verbose_toggles_mirroring():
    tg = FakeTelegram()
    log = DaemonLog(FrozenClock(), tg)
    log.set_verbose(True)
    log.log("x")
    assert len(tg.sent) == 1


def test_telegram_failure_is_swallowed():
    class Boom(FakeTelegram):
        def send(self, text):
            raise RuntimeError("down")

    log = DaemonLog(FrozenClock(), Boom(), verbose=True)
    log.log("still logs to stderr")  # must not raise
