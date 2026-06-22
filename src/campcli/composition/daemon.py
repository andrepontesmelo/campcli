"""Long-running availability poller. Composition root — wires concrete adapters."""
from __future__ import annotations

import sys
import time
import traceback

from ..infrastructure.api import BCParksClient
from ..infrastructure.clock import SystemClock
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
    clock = SystemClock()
    drive_times = load_drive_times()
    with HttpxTelegram(token=bot_token) as telegram, BCParksClient() as api:
        if profile is None:
            profile = load_profile(api)
        notifier = SearchNotifier(
            telegram=telegram,
            drive_times=drive_times,
            log=lambda msg: print(f"[{clock.now().isoformat(timespec='seconds')}] {msg}", file=sys.stderr),
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
        poller.start()
        while True:
            try:
                poller.tick()
                time.sleep(interval_secs)
            except KeyboardInterrupt:
                poller.log("interrupted, exiting")
                return
            except Exception as e:
                poller.log(f"poll iteration failed: {e}")
                traceback.print_exc(file=sys.stderr)
                time.sleep(interval_secs)
