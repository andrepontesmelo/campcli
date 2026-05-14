"""Long-running availability poller. Composition root — wires concrete adapters."""
from __future__ import annotations

import sys
import time
import traceback

from .api import BCParksClient
from .clock import SystemClock
from .constants import DB_PATH
from .drive_times import load_cache as load_drive_times
from .poller import Poller
from .store import SqliteStore
from .telegram import HttpxTelegram


def run_forever(
    *,
    bot_token: str,
    chat_id: str,
    interval_secs: float = 1.0,
    profile: dict | None = None,
) -> None:
    store = SqliteStore(DB_PATH)
    clock = SystemClock()
    drive_times = load_drive_times()
    with HttpxTelegram(token=bot_token, chat_id=chat_id) as telegram, BCParksClient() as api:
        poller = Poller(
            api=api, telegram=telegram,
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
