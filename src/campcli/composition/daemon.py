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
from ..application.daemon_log import WARNING
from ..application.poller import Poller
from ..application.search_notifier import SearchNotifier
from ..application.throttle import read_request_interval


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

    def _make_notifier(profile):
        return SearchNotifier(
            telegram=telegram,
            drive_times=drive_times,
            log=lambda *a: None,  # overridden by poller after construction
            not_interested_repo=store,
            rest_days=profile.rest_days_between_bookings,
        )

    with (
        HttpxTelegram(token=bot_token) as telegram,
        HttpxTelegram(token=bot_token) as poll_telegram,
        BCParksClient(min_interval_secs=interval) as api,
    ):
        poller = Poller(
            api=api, telegram=telegram,
            notifier_factory=_make_notifier,
            settings_repo=store, clock=clock,
            drive_times=drive_times,
            profile_repo=profile_repo,
            not_interested_repo=store,
        )
        poller.set_poll_telegram(poll_telegram)
        poller.start()
        stop = threading.Event()
        cmd_thread = threading.Thread(
            target=poller.handle_commands_forever,
            args=(stop,),
            daemon=True,
        )
        cmd_thread.start()
        while True:
            try:
                poller.run_search_once()
                time.sleep(interval_secs)
            except KeyboardInterrupt:
                poller.log("interrupted, exiting")
                stop.set()
                return
            except Exception as e:
                poller.log(f"poll iteration failed: {e}", WARNING)
                traceback.print_exc(file=sys.stderr)
                time.sleep(interval_secs)
