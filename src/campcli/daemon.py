"""Long-running availability poller. Composition root — wires concrete adapters."""
from __future__ import annotations

import sys
import time
import traceback

from .api import BCParksClient
from .poller import Poller
from .telegram import HttpxTelegram


def run_forever(
    *,
    bot_token: str,
    chat_id: str,
    interval_secs: float = 1.0,
    profile: dict | None = None,
) -> None:
    with HttpxTelegram(token=bot_token, chat_id=chat_id) as telegram, BCParksClient() as api:
        poller = Poller(api=api, telegram=telegram, profile=profile)
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
