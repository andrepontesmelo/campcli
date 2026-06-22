"""DaemonLog — the daemon's log sink.

Owns the one logging concern: every line goes to stderr, and for each chat
in the verbose_chats set it is also mirrored to Telegram. Verbose state is
per-chat, stored in a set of chat_ids.
"""
from __future__ import annotations

from ..domain.ports import Clock, Telegram


class DaemonLog:
    def __init__(
        self,
        clock: Clock,
        telegram: Telegram,
        *,
        verbose_chats: set[str] | None = None,
    ) -> None:
        self._clock = clock
        self._telegram = telegram
        self._verbose_chats: set[str] = verbose_chats or set()

    def set_verbose_chats(self, chats: set[str]) -> None:
        self._verbose_chats = set(chats)

    def set_verbose(self, chat_id: str, on: bool) -> None:
        if on:
            self._verbose_chats.add(chat_id)
        else:
            self._verbose_chats.discard(chat_id)

    def log(self, msg: str) -> None:
        import sys

        line = f"[{self._clock.now().isoformat(timespec='seconds')}] {msg}"
        print(line, file=sys.stderr, flush=True)
        for chat_id in self._verbose_chats:
            try:
                self._telegram.send_to(chat_id, line)
            except Exception:
                pass

    __call__ = log
