"""Authorized Telegram user management.

Domain logic for checking authorization against tg_allowed_ids,
building per-user verbose chat sets, and generating unauthorized replies.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..domain.ports import SettingsRepo


def is_authorized(tg_id: int, allowed_ids: list[int]) -> bool:
    """Return True if tg_id is in the allowed list (or list is empty)."""
    return tg_id in allowed_ids


def unauthorized_reply(tg_id: int) -> str:
    """Return a message telling the user their Telegram ID."""
    return (
        f"Your Telegram ID is {tg_id}. "
        f"Ask an admin to run: campcli telegram allow {tg_id}"
    )


def build_verbose_chat_set(
    settings_repo: SettingsRepo, allowed_ids: list[int]
) -> set[str]:
    """Build set of chat_ids that have per-user verbose ON.

    Reads verbose:{tg_id} and chat:{tg_id} from settings for each
    allowed user. Returns set of chat_ids that should receive verbose logs.
    """
    chats: set[str] = set()
    for tg_id in allowed_ids:
        val = settings_repo.get_setting(f"verbose:{tg_id}")
        if val == "on":
            chat = settings_repo.get_setting(f"chat:{tg_id}")
            if chat:
                chats.add(chat)
    return chats
