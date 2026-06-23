"""Long-running availability poller. Composition root — wires concrete adapters."""
from __future__ import annotations

import sys
import threading
import time
import traceback

from ..infrastructure.api import BCParksClient
from ..infrastructure.clock import SystemClock
from ..application.throttle import read_request_interval
from ..constants import DB_PATH
from ..infrastructure.drive_times_cache import load_cache as load_drive_times
from ..application.poller import Poller
from ..application.profile import Profile, load_profile
from ..application.search_notifier import SearchNotifier
from ..infrastructure.store import SqliteStore
from ..infrastructure.telegram import HttpxTelegram


def run_forever(
    *,
    bot_token: str,
    interval_secs: float = 1.0,
    profile: Profile | None = None,
) -> None:
    store = SqliteStore(DB_PATH)
    interval = read_request_interval(store)
    clock = SystemClock()
    drive_times = load_drive_times()
    with (
        HttpxTelegram(token=bot_token) as telegram,
        HttpxTelegram(token=bot_token) as poll_telegram,
        BCParksClient(min_interval_secs=interval) as api,
    ):
        if profile is None:
            profile = load_profile(api)
        notifier = SearchNotifier(
            telegram=telegram,
            drive_times=drive_times,
            log=lambda msg: None,
            rest_days=profile.rest_days_between_bookings,
        )
        poller = Poller(
            api=api, telegram=telegram,
            notifier=notifier,
            booking_repo=store, blocked_repo=store,
            settings_repo=store, clock=clock,
            drive_times=drive_times,
            profile=profile,
        )
        notifier.set_log(poller.log)
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
                poller.log(f"poll iteration failed: {e}")
                traceback.print_exc(file=sys.stderr)
                time.sleep(interval_secs)
