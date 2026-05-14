"""Dispatch table for daemon Telegram commands.

Add a new command: write a handler function, add it to COMMANDS.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .poller import Poller


def _cmd_verbose_on(poller: Poller) -> str:
    poller.set_verbose(True)
    return "verbose logging ON"


def _cmd_verbose_off(poller: Poller) -> str:
    poller.set_verbose(False)
    return "verbose logging OFF"


COMMANDS: dict[str, Callable[[Poller], str]] = {
    "/verbose on": _cmd_verbose_on,
    "/verbose off": _cmd_verbose_off,
}


def dispatch(text: str, poller: Poller) -> str | None:
    handler = COMMANDS.get(text.strip())
    return handler(poller) if handler else None
