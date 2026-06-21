"""DaemonLog — the daemon's log sink.

Owns the one logging concern: every line goes to stderr, and when verbose is on
it is also mirrored to Telegram. Verbose is the sink's own state, so the Poller
no longer carries logging behaviour. A test can inject a silent sink instead of
asserting on stderr — the seam is real, not hypothetical.
"""
from __future__ import annotations

from ..domain.ports import Clock, Telegram


class DaemonLog:
    def __init__(self, clock: Clock, telegram: Telegram, *, verbose: bool = False) -> None:
        self._clock = clock
        self._telegram = telegram
        self._verbose = verbose

    @property
    def verbose(self) -> bool:
        return self._verbose

    def set_verbose(self, on: bool) -> None:
        self._verbose = on

    def log(self, msg: str) -> None:
        import sys

        line = f"[{self._clock.now().isoformat(timespec='seconds')}] {msg}"
        print(line, file=sys.stderr, flush=True)
        if self._verbose:
            try:
                self._telegram.send(line)
            except Exception:
                pass

    __call__ = log
