"""DaemonLog — the daemon's log sink.

Owns the one logging concern: lines at or above min_level go to stderr, and
every line (regardless of level) is mirrored to each chat in the verbose_chats
set — that mirror is the /verbose feature and must stay chatty. Verbose state
is per-chat, stored in a set of chat_ids.
"""
from __future__ import annotations

from ..domain.ports import Clock, Telegram

INFO = 20
WARNING = 30


class DaemonLog:
    def __init__(
        self,
        clock: Clock,
        telegram: Telegram,
        *,
        verbose_chats: set[str] | None = None,
        min_level: int = WARNING,
    ) -> None:
        self._clock = clock
        self._telegram = telegram
        self._verbose_chats: set[str] = verbose_chats or set()
        self._min_level = min_level

    def set_verbose_chats(self, chats: set[str]) -> None:
        self._verbose_chats = set(chats)

    def set_verbose(self, chat_id: str, on: bool) -> None:
        if on:
            self._verbose_chats.add(chat_id)
        else:
            self._verbose_chats.discard(chat_id)

    def log(self, msg: str, level: int = INFO) -> None:
        import sys

        line = f"[{self._clock.now().isoformat(timespec='seconds')}] {msg}"
        if level >= self._min_level:
            print(line, file=sys.stderr, flush=True)
        for chat_id in self._verbose_chats:
            try:
                self._telegram.send_to(chat_id, line)
            except Exception as e:
                print(f"telegram send to {chat_id} failed: {e}", file=sys.stderr)

    __call__ = log
