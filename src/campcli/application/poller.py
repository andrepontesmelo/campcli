"""Poller — Application service for daemon poll-and-notify loop.

Multi-profile: loads all enabled profiles from ``ProfileRepo``, deduplicates
park/map API calls across profiles, and notifies per-profile.
"""
from __future__ import annotations

from collections.abc import Callable

from . import command_router, telegram_settings
from .daemon_log import DaemonLog, INFO, WARNING
from .command_responses import handle_one_command_batch  # noqa: F401
from ..domain.models import DriveTimes
from .telegram_users import build_verbose_chat_set
from ..domain.models import Profile
from ..domain.ports import BCParksApi, Clock, NotInterestedRepo, ProfileRepo, SettingsRepo, Telegram
from .search_notifier import SearchNotifier
from .search_loop import run_search_once as _run_search_once


class Poller:
    def __init__(
        self,
        *,
        api: BCParksApi,
        telegram: Telegram,
        notifier_factory: Callable[[Profile], SearchNotifier],
        settings_repo: SettingsRepo,
        clock: Clock,
        drive_times: DriveTimes,
        profile_repo: ProfileRepo,
        not_interested_repo: NotInterestedRepo | None = None,
    ) -> None:
        self._api = api
        self._telegram = telegram
        self._notifier_factory = notifier_factory
        self._settings_repo = settings_repo
        self._clock = clock
        self._drive_times = drive_times
        self._profile_repo = profile_repo
        self._not_interested_repo = not_interested_repo

        # Cache of per-profile notifiers — persists across poll cycles so
        # NotificationPolicy dedup state (seen set) carries over.
        self._notifiers: dict[int, SearchNotifier] = {}

        # Union of all enabled profiles' tg_allowed_ids (for command auth).
        self._tg_allowed_ids: list[int] = []
        self._refresh_tg_allowed_ids()

        verbose_chats = build_verbose_chat_set(
            self._settings_repo, self._tg_allowed_ids
        )
        self._log = DaemonLog(clock, telegram, verbose_chats=verbose_chats)
        self._poll_telegram: Telegram | None = None

    def _refresh_tg_allowed_ids(self) -> None:
        """Recompute the union of ``tg_allowed_ids`` across enabled profiles."""
        self._tg_allowed_ids = telegram_settings.refresh_tg_allowed_ids(
            self._profile_repo
        )

    def set_poll_telegram(self, poll_telegram: Telegram) -> None:
        self._poll_telegram = poll_telegram

    def start(self) -> None:
        # Register bot commands
        try:
            self._telegram.set_my_commands(command_router.BOT_COMMANDS)
        except Exception as e:
            self.log(f"setMyCommands failed: {e}", WARNING)
        # Notify all authorized users who have a known chat
        for tg_id in self._tg_allowed_ids:
            chat = telegram_settings.get_chat_id(self._settings_repo, tg_id)
            if chat:
                try:
                    self._telegram.send_to(
                        chat, "campcli daemon started v3"
                    )
                except Exception as e:
                    self.log(f"startup telegram to {tg_id} failed: {e}", WARNING)

    def run_search_once(self) -> None:
        self._refresh_tg_allowed_ids()
        _run_search_once(
            api=self._api,
            profile_repo=self._profile_repo,
            settings_repo=self._settings_repo,
            drive_times=self._drive_times,
            not_interested_repo=self._not_interested_repo,
            clock=self._clock,
            notifier_factory=self._notifier_factory,
            notifiers=self._notifiers,
            log=self.log,
        )

    def _get_verbose(self, tg_id: int) -> bool:
        return telegram_settings.get_verbose(self._settings_repo, tg_id)

    def set_verbose(self, tg_id: int, on: bool, chat_id: str | None = None) -> None:
        telegram_settings.set_verbose(self._settings_repo, tg_id, on)
        if chat_id:
            self._log.set_verbose(chat_id, on)
        self._refresh_verbose_chats()

    def _refresh_verbose_chats(self) -> None:
        chats = build_verbose_chat_set(
            self._settings_repo, self._tg_allowed_ids
        )
        self._log.set_verbose_chats(chats)

    def _get_chat_id_for_user(self, tg_id: int) -> str | None:
        return telegram_settings.get_chat_id(self._settings_repo, tg_id)

    def log(self, msg: str, level: int = INFO) -> None:
        self._log.log(msg, level)


