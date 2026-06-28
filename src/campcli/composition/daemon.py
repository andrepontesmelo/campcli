"""Long-running availability poller. Composition root — wires concrete adapters."""
from __future__ import annotations

import sys
import threading
import time
import traceback

from ..constants import DB_PATH, PROFILE_PATH
from ..infrastructure.api import BCParksClient
from ..infrastructure.clock import SystemClock
from ..infrastructure.drive_times_cache import load_cache as load_drive_times
from ..infrastructure.store import SqliteStore
from ..infrastructure.telegram import HttpxTelegram
from ..application.migrate_profile import migrate_profile_json_to_db
from ..application.command_router import BOT_COMMANDS, CommandContext
from ..application.command_responses import handle_commands_forever
from ..application.daemon_log import INFO, WARNING, DaemonLog
from ..application.search_loop import run_search_once
from ..application.search_notifier import SearchNotifier
from ..application import telegram_settings
from ..application.telegram_users import build_verbose_chat_set
from ..application.throttle import read_request_interval
from ..presentation.format import render_match_message


def startup(
    *,
    telegram,
    tg_allowed_ids: list[int],
    settings_repo,
    log,
) -> None:
    """Register bot commands and send startup notification messages."""
    try:
        telegram.set_my_commands(BOT_COMMANDS)
    except Exception as e:
        log(f"setMyCommands failed: {e}", WARNING)
    for tg_id in tg_allowed_ids:
        chat = telegram_settings.get_chat_id(settings_repo, tg_id)
        if chat:
            try:
                telegram.send_to(chat, "campcli daemon started v3")
            except Exception as e:
                log(f"startup telegram to {tg_id} failed: {e}", WARNING)


def run_forever(
    *,
    bot_token: str,
    interval_secs: float = 1.0,
) -> None:
    store = SqliteStore(DB_PATH)
    store.purge_old_sent_notifications()
    interval = read_request_interval(store)
    clock = SystemClock()
    drive_times = load_drive_times()

    # --- multi-profile setup ---
    profile_repo: SqliteStore = store  # SqliteStore satisfies ProfileRepo
    migrate_profile_json_to_db(PROFILE_PATH, profile_repo)

    # --- tg_allowed_ids: mutable list refreshed each poll cycle ---
    tg_allowed_ids: list[int] = telegram_settings.refresh_tg_allowed_ids(
        profile_repo
    )

    def _make_notifier(profile):
        return SearchNotifier(
            telegram=telegram,
            drive_times=drive_times,
            log=lambda *a: None,  # overridden by SearchNotifier.set_log
            render_match_message=render_match_message,
            not_interested_repo=store,
            rest_days=profile.rest_days_between_bookings,
        )

    # Mutable box for on_request — replaced with real logger after daemon_log
    # is constructed (avoids reordering the with-block managers).
    _api_on_request = [lambda *a: None]

    def _on_request(path, params, status, summary):
        _api_on_request[0](path, params, status, summary)

    with (
        HttpxTelegram(token=bot_token) as telegram,
        HttpxTelegram(token=bot_token) as poll_telegram,
        BCParksClient(min_interval_secs=interval, on_request=_on_request) as api,
    ):
        # --- DaemonLog ---
        verbose_chats = build_verbose_chat_set(store, tg_allowed_ids)
        daemon_log = DaemonLog(clock, telegram, verbose_chats=verbose_chats)

        # Replace the noop placeholder — subsequent API calls are logged.
        def _api_req_logger(path, params, status, summary):
            pstr = "?" + "&".join(f"{k}={v}" for k, v in sorted(params.items())) if params else ""
            daemon_log.log(f"API GET {path}{pstr} → {status} ({summary})", INFO)

        _api_on_request[0] = _api_req_logger

        def log(msg: str, level: int = INFO) -> None:
            daemon_log.log(msg, level)

        def refresh_verbose_chats() -> None:
            chats = build_verbose_chat_set(store, tg_allowed_ids)
            daemon_log.set_verbose_chats(chats)

        # --- CommandContext (replaces Poller) ---
        ctx = CommandContext(
            api=api,
            settings_repo=store,
            profile_repo=profile_repo,
            not_interested_repo=store,
            _refresh_verbose_chats=refresh_verbose_chats,
        )

        # --- startup ---
        startup(
            telegram=telegram,
            tg_allowed_ids=tg_allowed_ids,
            settings_repo=store,
            log=log,
        )

        # --- command processing thread ---
        stop = threading.Event()
        cmd_thread = threading.Thread(
            target=handle_commands_forever,
            args=(stop,),
            kwargs=dict(
                ctx=ctx,
                telegram=telegram,
                settings_repo=store,
                log=log,
                refresh_verbose_chats=refresh_verbose_chats,
                poll_telegram=poll_telegram,
                tg_allowed_ids=tg_allowed_ids,
            ),
            daemon=True,
        )
        cmd_thread.start()

        # Cache of per-profile notifiers — persists across poll cycles so
        # NotificationPolicy dedup state (seen set) carries over.
        notifiers: dict[int, SearchNotifier] = {}
        while True:
            try:
                # Refresh allowed IDs before each poll cycle (in-place
                # mutation so the command thread sees the latest list).
                tg_allowed_ids[:] = telegram_settings.refresh_tg_allowed_ids(
                    profile_repo
                )
                run_search_once(
                    api=api,
                    profile_repo=store,
                    settings_repo=store,
                    drive_times=drive_times,
                    not_interested_repo=store,
                    clock=clock,
                    notifier_factory=_make_notifier,
                    notifiers=notifiers,
                    log=log,
                )
                time.sleep(interval_secs)
            except KeyboardInterrupt:
                log("interrupted, exiting")
                stop.set()
                return
            except Exception as e:
                log(f"poll iteration failed: {e}", WARNING)
                traceback.print_exc(file=sys.stderr)
                time.sleep(interval_secs)
