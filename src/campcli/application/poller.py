"""Poller — Application service for daemon poll-and-notify loop."""
from __future__ import annotations

import threading
import time

from . import command_router
from .daemon_log import DaemonLog
from .drive_times import DriveTimes
from .telegram_users import build_verbose_chat_set
from ..domain.ports import (
    BCParksApi,
    Clock,
    SettingsRepo,
    Telegram,
)
from .profile import Profile
from .search import run as run_search
from .search_notifier import SearchNotifier


class Poller:
    def __init__(
        self,
        *,
        api: BCParksApi,
        telegram: Telegram,
        notifier: SearchNotifier,
        settings_repo: SettingsRepo,
        clock: Clock,
        drive_times: DriveTimes,
        profile: Profile | None = None,
    ) -> None:
        self._api = api
        self._telegram = telegram
        self._notifier = notifier
        self._settings_repo = settings_repo
        self._clock = clock
        self._drive_times = drive_times
        self._profile = profile or Profile()
        self._tg_allowed_ids = self._profile.tg_allowed_ids
        verbose_chats = build_verbose_chat_set(
            self._settings_repo, self._tg_allowed_ids
        )
        self._log = DaemonLog(clock, telegram, verbose_chats=verbose_chats)
        self._poll_telegram: Telegram | None = None
        self._update_offset: int | None = None

    def set_poll_telegram(self, poll_telegram: Telegram) -> None:
        self._poll_telegram = poll_telegram

    def start(self) -> None:
        # Register bot commands
        try:
            self._telegram.set_my_commands(command_router.BOT_COMMANDS)
        except Exception as e:
            self.log(f"setMyCommands failed: {e}")
        # Notify all authorized users who have a known chat
        for tg_id in self._tg_allowed_ids:
            chat = self._settings_repo.get_setting(f"chat:{tg_id}")
            if chat:
                try:
                    self._telegram.send_to(
                        chat, "campcli daemon started v3"
                    )
                except Exception as e:
                    self.log(f"startup telegram to {tg_id} failed: {e}")

    def tick(self) -> None:
        self._handle_commands()
        self.run_search_once()

    def run_search_once(self) -> None:
        self._notifier.start_poll([], set())
        self.log("poll start")

        allowed_ids = self._profile.allowed_park_ids or None
        for match in run_search(
            self._api,
            self._profile,
            drive_times=self._drive_times,
            allowed_park_ids=allowed_ids,
            progress=self.log,
        ):
            # Build list of chat_ids for authorized users with known chats
            chat_ids = [
                cid for cid in (
                    self._settings_repo.get_setting(f"chat:{tid}")
                    for tid in self._tg_allowed_ids
                )
                if cid is not None
            ]
            self._notifier.notify(match, chat_ids=chat_ids)

    def handle_commands_forever(
        self, stop: threading.Event, long_poll_timeout: int = 25
    ) -> None:
        poll = self._poll_telegram or self._telegram
        while not stop.is_set():
            try:
                updates = poll.poll_updates(
                    offset=self._update_offset,
                    long_poll_timeout=long_poll_timeout,
                )
                for upd in updates:
                    self._process_update(upd)
            except Exception as e:
                self.log(f"command loop error: {e}")
                time.sleep(1)

    def _get_verbose(self, tg_id: int) -> bool:
        val = self._settings_repo.get_setting(f"verbose:{tg_id}")
        return val == "on"

    def set_verbose(self, tg_id: int, on: bool, chat_id: str | None = None) -> None:
        self._settings_repo.set_setting(
            f"verbose:{tg_id}", "on" if on else "off"
        )
        if chat_id:
            self._log.set_verbose(chat_id, on)
        self._refresh_verbose_chats()

    def _refresh_verbose_chats(self) -> None:
        chats = build_verbose_chat_set(
            self._settings_repo, self._tg_allowed_ids
        )
        self._log.set_verbose_chats(chats)

    def _get_chat_id_for_user(self, tg_id: int) -> str | None:
        return self._settings_repo.get_setting(f"chat:{tg_id}")

    def log(self, msg: str) -> None:
        self._log.log(msg)

    def _handle_commands(self) -> None:
        updates = self._telegram.poll_updates(offset=self._update_offset)
        for upd in updates:
            self._process_update(upd)

    def _process_update(self, upd) -> None:
        self._update_offset = upd.update_id + 1
        self.log(f"received update: {upd.text or '(callback)'!r}")
        # Last-seen chat tracking (authorized users only)
        if (
            upd.from_id is not None
            and upd.chat_id
            and upd.from_id in self._tg_allowed_ids
        ):
            old = self._settings_repo.get_setting(
                f"chat:{upd.from_id}"
            )
            if old != upd.chat_id:
                self._settings_repo.set_setting(
                    f"chat:{upd.from_id}", upd.chat_id
                )
                self._refresh_verbose_chats()
        result = command_router.dispatch(
            upd, self, self._tg_allowed_ids
        )
        if result is None:
            # Still answer the callback query if applicable
            if upd.callback_query_id:
                try:
                    self._telegram.answer_callback_query(
                        upd.callback_query_id
                    )
                except Exception:
                    pass
            return
        # Always answer callback queries to dismiss the Telegram spinner,
        # even for unauthorized users (dispatch may return "reply" type).
        if upd.callback_query_id and result.get("type") != "callback":
            try:
                self._telegram.answer_callback_query(
                    upd.callback_query_id
                )
            except Exception:
                pass
        t = result.get("type")
        if t == "reply":
            text = result["text"]
            self._telegram.send_to(upd.chat_id, text)
            self.log(f"replied: {text}")
        elif t == "inline_keyboard":
            text = result["text"]
            buttons = result["buttons"]
            self._telegram.send_inline_keyboard(
                upd.chat_id, text, buttons
            )
            self.log(f"sent inline keyboard: {text}")
        elif t == "callback":
            cb_id = result.get("callback_query_id", "")
            text = result.get("text", "")
            # Answer callback query to dismiss spinner
            try:
                self._telegram.answer_callback_query(cb_id)
            except Exception:
                pass
            # Edit the original message to reflect new state
            msg_id = upd.message_id
            if msg_id:
                try:
                    self._telegram.edit_message_reply_markup(
                        upd.chat_id, msg_id, text=text
                    )
                except Exception:
                    pass
            self.log(f"callback answered: {text}")
