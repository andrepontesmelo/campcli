"""Dispatch table for daemon Telegram commands.

Add a new command: write a handler function, add it to COMMANDS dict.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..domain.ports import BotCommand, TelegramUpdate

if TYPE_CHECKING:
    from .poller import Poller


# Result from dispatch: action dict with type discriminator.
#   {"type": "reply", "text": str}
#   {"type": "inline_keyboard", "text": str, "buttons": [[{"text": str, "callback_data": str}]]}
#   {"type": "callback", "text": str}
#   None  (no action)
DispatchResult = dict[str, Any] | None


def _cmd_verbose_bare(tg_id: int, poller: Poller) -> DispatchResult:
    """Show current verbose state with inline keyboard."""
    current = poller._get_verbose(tg_id)
    state = "ON" if current else "OFF"
    buttons = [
        [
            {"text": "ON", "callback_data": "verbose_on"},
            {"text": "OFF", "callback_data": "verbose_off"},
        ]
    ]
    return {
        "type": "inline_keyboard",
        "text": f"verbose logging for your account: {state}",
        "buttons": buttons,
    }


def _cmd_verbose_on(tg_id: int, poller: Poller) -> DispatchResult:
    poller.set_verbose(tg_id, True)
    return {"type": "reply", "text": "verbose logging ON"}


def _cmd_verbose_off(tg_id: int, poller: Poller) -> DispatchResult:
    poller.set_verbose(tg_id, False)
    return {"type": "reply", "text": "verbose logging OFF"}


COMMANDS: dict[str, str] = {
    "/verbose": "verbose_bare",
    "/verbose on": "verbose_on",
    "/verbose off": "verbose_off",
}

# Commands to register via setMyCommands
BOT_COMMANDS: list[BotCommand] = [
    BotCommand(command="verbose", description="Toggle verbose daemon logging"),
]

CB_HANDLERS: dict[str, str] = {
    "verbose_on": "verbose_on",
    "verbose_off": "verbose_off",
}


def dispatch(
    update: TelegramUpdate, poller: Poller, tg_allowed_ids: list[int]
) -> DispatchResult:
    """Route a TelegramUpdate to the right handler.

    Returns action dict or None for unknown/unhandled.
    """
    from_id = update.from_id
    if from_id is not None and from_id not in tg_allowed_ids:
        return {
            "type": "reply",
            "text": (
                f"Your Telegram ID is {from_id}. "
                f"Ask an admin to run: campcli telegram allow {from_id}"
            ),
        }

    # Callback query dispatch
    if update.callback_query_id and update.callback_data:
        action = CB_HANDLERS.get(update.callback_data)
        if action and from_id is not None:
            if action == "verbose_on":
                poller.set_verbose(from_id, True)
            elif action == "verbose_off":
                poller.set_verbose(from_id, False)
            return {
                "type": "callback",
                "callback_query_id": update.callback_query_id,
                "text": f"verbose logging for your account: {'ON' if action == 'verbose_on' else 'OFF'}",
            }
        return {"type": "reply", "text": "unknown command"}

    # Text command dispatch
    text = (update.text or "").strip()
    cmd_name = COMMANDS.get(text)
    if cmd_name is None:
        return None
    if from_id is None:
        return {"type": "reply", "text": "could not identify user"}
    if cmd_name == "verbose_bare":
        return _cmd_verbose_bare(from_id, poller)
    if cmd_name == "verbose_on":
        return _cmd_verbose_on(from_id, poller)
    if cmd_name == "verbose_off":
        return _cmd_verbose_off(from_id, poller)
    return None
