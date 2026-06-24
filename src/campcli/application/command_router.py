"""Dispatch table for daemon Telegram commands.

Add a new command: write a handler function, add it to COMMANDS dict.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..domain.ports import BotCommand, TelegramUpdate
from .catalog import find_park
from .telegram_users import is_authorized, unauthorized_reply

if TYPE_CHECKING:
    from .poller import Poller


# Result from dispatch: action dict with type discriminator.
#   {"type": "reply", "text": str}
#   {"type": "inline_keyboard", "text": str, "buttons": [[{"text": str, "callback_data": str}]]}
#   {"type": "callback", "text": str}
#   None  (no action)
DispatchResult = dict[str, Any] | None


def _cmd_not_interested(update: TelegramUpdate, poller: Poller) -> DispatchResult:
    if update.reply_to_message_id is None:
        return {"type": "reply", "text": "Reply this command to a notification message."}
    ni_repo = poller._not_interested_repo
    if ni_repo is None:
        return {"type": "reply", "text": "NotInterested is not configured."}
    entry = ni_repo.lookup_sent(update.reply_to_message_id)
    if entry is None:
        return {"type": "reply", "text": "Could not find the notification for this message (may have been purged)."}
    profile_id, park_id, date_start, date_end = entry
    profile = poller._profile_repo.get_by_id(profile_id)
    if profile is None:
        return {"type": "reply", "text": "Could not find your profile."}
    if update.from_id not in profile.tg_allowed_ids:
        return {"type": "reply", "text": "Not authorized."}
    try:
        ni_repo.add(
            profile_id=profile_id, park_id=park_id,
            date_start=date_start, date_end=date_end,
        )
    except ValueError:
        return {"type": "reply", "text": "Already marked not interested."}
    parks = poller._api.list_parks()
    park = find_park(parks, park_id)
    park_name = park.name if park else f"park #{park_id}"
    return {
        "type": "reply",
        "text": f"NotInterested recorded: {park_name} {date_start} – {date_end}",
    }


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
    "/not-interested": "not_interested",
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
    if from_id is not None and not is_authorized(from_id, tg_allowed_ids):
        return {"type": "reply", "text": unauthorized_reply(from_id)}

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
    if cmd_name == "not_interested":
        return _cmd_not_interested(update, poller)
    return None
