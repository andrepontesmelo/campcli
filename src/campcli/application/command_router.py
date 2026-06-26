"""Dispatch table for daemon Telegram commands.

Add a new command: write a handler function, add it to COMMANDS dict.
"""
from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from ..domain.ports import BotCommand, TelegramUpdate
from .catalog import find_park
from .telegram_users import is_authorized, unauthorized_reply

if TYPE_CHECKING:
    from ..domain.ports import BCParksApi, NotInterestedRepo, ProfileRepo, SettingsRepo


# Result from dispatch: action dict with type discriminator.
#   {"type": "reply", "text": str}
#   {"type": "inline_keyboard", "text": str, "buttons": [[{"text": str, "callback_data": str}]]}
#   {"type": "callback", "text": str}
#   None  (no action)
DispatchResult = dict[str, Any] | None


@dataclass
class CommandContext:
    """Holds dependencies needed by command_router dispatch handlers.

    Replaces the dissolved ``Poller`` class — a lightweight data holder
    that the composition root assembles and the command router consumes.
    """

    api: "BCParksApi"
    settings_repo: "SettingsRepo"
    profile_repo: "ProfileRepo"
    not_interested_repo: "NotInterestedRepo | None" = None
    # Callback to rebuild the verbose-chat set after a verbose toggle.
    _refresh_verbose_chats: Callable[[], None] = lambda: None

    def get_verbose(self, tg_id: int) -> bool:
        from . import telegram_settings

        return telegram_settings.get_verbose(self.settings_repo, tg_id)

    def set_verbose(self, tg_id: int, on: bool) -> None:
        from . import telegram_settings

        telegram_settings.set_verbose(self.settings_repo, tg_id, on)
        self._refresh_verbose_chats()


def _cmd_not_interested(update: TelegramUpdate, ctx: CommandContext) -> DispatchResult:
    if update.reply_to_message_id is None:
        return {"type": "reply", "text": "Reply this command to a notification message."}
    ni_repo = ctx.not_interested_repo
    if ni_repo is None:
        return {"type": "reply", "text": "NotInterested is not configured."}
    entry = ni_repo.lookup_sent(update.reply_to_message_id)
    if entry is None:
        return {"type": "reply", "text": "Could not find the notification for this message (may have been purged)."}
    profile_id, park_id, date_start, date_end = entry
    profile = ctx.profile_repo.get_by_id(profile_id)
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
    parks = ctx.api.list_parks()
    park = find_park(parks, park_id)
    park_name = park.name if park else f"park #{park_id}"
    return {
        "type": "reply",
        "text": f"NotInterested recorded: {park_name} {date_start} – {date_end}",
    }


def _cmd_verbose_bare(tg_id: int, ctx: CommandContext) -> DispatchResult:
    """Show current verbose state with inline keyboard."""
    current = ctx.get_verbose(tg_id)
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


def _cmd_verbose_on(tg_id: int, ctx: CommandContext) -> DispatchResult:
    ctx.set_verbose(tg_id, True)
    return {"type": "reply", "text": "verbose logging ON"}


def _cmd_verbose_off(tg_id: int, ctx: CommandContext) -> DispatchResult:
    ctx.set_verbose(tg_id, False)
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
    update: TelegramUpdate, ctx: CommandContext, tg_allowed_ids: list[int]
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
                ctx.set_verbose(from_id, True)
            elif action == "verbose_off":
                ctx.set_verbose(from_id, False)
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
        return _cmd_verbose_bare(from_id, ctx)
    if cmd_name == "verbose_on":
        return _cmd_verbose_on(from_id, ctx)
    if cmd_name == "verbose_off":
        return _cmd_verbose_off(from_id, ctx)
    if cmd_name == "not_interested":
        return _cmd_not_interested(update, ctx)
    return None
