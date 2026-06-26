"""Module-level functions for Telegram command response handling.

Extracted from ``Poller`` so that command processing is testable without
constructing a full Poller (which needs api, telegram, notifier_factory,
profile_repo, etc.).
"""
from __future__ import annotations

import threading
import time
from collections.abc import Callable

from . import command_router, telegram_settings
from .daemon_log import INFO, WARNING


def process_update(
    upd,
    *,
    poller,
    telegram,
    settings_repo,
    tg_allowed_ids: list[int],
    log: Callable[..., None],
    refresh_verbose_chats: Callable[[], None],
) -> int:
    """Process a single Telegram update, returning the new update_offset.

    Handles all dispatch result types: reply, inline_keyboard, callback.
    """
    new_offset = upd.update_id + 1
    log(f"received update: {upd.text or '(callback)'!r}")

    # Last-seen chat tracking (authorized users only)
    if (
        upd.from_id is not None
        and upd.chat_id
        and upd.from_id in tg_allowed_ids
    ):
        old = telegram_settings.get_chat_id(settings_repo, upd.from_id)
        if old != upd.chat_id:
            telegram_settings.set_chat_id(
                settings_repo, upd.from_id, upd.chat_id
            )
            refresh_verbose_chats()

    result = command_router.dispatch(upd, poller, tg_allowed_ids)

    if result is None:
        # Still answer the callback query if applicable
        if upd.callback_query_id:
            try:
                telegram.answer_callback_query(upd.callback_query_id)
            except Exception:
                pass
        return new_offset

    # Always answer callback queries to dismiss the Telegram spinner,
    # even for unauthorized users (dispatch may return "reply" type).
    if upd.callback_query_id and result.get("type") != "callback":
        try:
            telegram.answer_callback_query(upd.callback_query_id)
        except Exception:
            pass

    t = result.get("type")
    if t == "reply":
        text = result["text"]
        telegram.send_to(upd.chat_id, text)
        log(f"replied: {text}")
    elif t == "inline_keyboard":
        text = result["text"]
        buttons = result["buttons"]
        telegram.send_inline_keyboard(upd.chat_id, text, buttons)
        log(f"sent inline keyboard: {text}")
    elif t == "callback":
        cb_id = result.get("callback_query_id", "")
        text = result.get("text", "")
        # Answer callback query to dismiss spinner
        try:
            telegram.answer_callback_query(cb_id)
        except Exception:
            pass
        # Edit the original message to reflect new state
        msg_id = upd.message_id
        if msg_id:
            try:
                telegram.edit_message_reply_markup(
                    upd.chat_id, msg_id, text=text
                )
            except Exception:
                pass
        log(f"callback answered: {text}")

    return new_offset


def handle_commands_forever(
    stop: threading.Event,
    *,
    poller,
    telegram,
    settings_repo,
    log: Callable[..., None],
    refresh_verbose_chats: Callable[[], None],
    poll_telegram=None,
    long_poll_timeout: int = 25,
) -> None:
    """Poll for and process Telegram commands until *stop* is set.

    Args:
        stop: Event that signals shutdown.
        poller: Poller instance (needed by command_router.dispatch).
        telegram: Telegram adapter for sending responses.
        settings_repo: For chat tracking.
        log: Logging callable (msg, level=INFO).
        refresh_verbose_chats: Callback to rebuild verbose chat set
            after chat_id change.
        poll_telegram: Separate Telegram adapter for polling
            (if different from sending).
        long_poll_timeout: Seconds for long-polling.
    """
    poll = poll_telegram or telegram
    update_offset: int | None = None
    while not stop.is_set():
        try:
            updates = poll.poll_updates(
                offset=update_offset,
                long_poll_timeout=long_poll_timeout,
            )
            for upd in updates:
                update_offset = process_update(
                    upd,
                    poller=poller,
                    telegram=telegram,
                    settings_repo=settings_repo,
                    tg_allowed_ids=poller._tg_allowed_ids,
                    log=log,
                    refresh_verbose_chats=refresh_verbose_chats,
                )
        except Exception as e:
            log(f"command loop error: {e}", WARNING)
            time.sleep(1)


def handle_one_command_batch(
    poller,
    *,
    telegram=None,
    settings_repo=None,
    tg_allowed_ids=None,
    log=None,
    refresh_verbose_chats=None,
    update_offset=None,
) -> int | None:
    """Process one batch of Telegram updates.

    Keeps the Poller-based signature for backward compatibility
    (used by tests). Explicit keyword args override Poller attributes.

    Returns the last update_offset processed, or None if no updates.
    """
    t = telegram or poller._telegram
    sr = settings_repo or poller._settings_repo
    ids = tg_allowed_ids or poller._tg_allowed_ids
    lf = log or poller.log
    rvc = refresh_verbose_chats or poller._refresh_verbose_chats

    current_offset = (
        update_offset
        if update_offset is not None
        else getattr(poller, "_update_offset", None)
    )
    updates = t.poll_updates(offset=current_offset)
    last_offset = current_offset
    for upd in updates:
        last_offset = process_update(
            upd,
            poller=poller,
            telegram=t,
            settings_repo=sr,
            tg_allowed_ids=ids,
            log=lf,
            refresh_verbose_chats=rvc,
        )
    return last_offset
