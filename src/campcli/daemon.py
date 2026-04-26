"""Long-running availability poller. Pushes Telegram messages ASAP per match."""
from __future__ import annotations

import sys
import time
import traceback
from datetime import date, datetime

import httpx

from . import filters, store
from .api import BCParksClient
from .constants import DEFAULT_PROFILE
from .models import WeekendMatch
from .notify import format_match_message, send_telegram
from .search import run as run_search


def _log(msg: str) -> None:
    print(f"[{datetime.now().isoformat(timespec='seconds')}] {msg}", file=sys.stderr, flush=True)


def run_forever(
    *,
    bot_token: str,
    chat_id: str,
    interval_secs: float = 1.0,
    profile: dict | None = None,
) -> None:
    profile = profile or DEFAULT_PROFILE
    seen: set[tuple[int, int, date, int]] = set()

    with httpx.Client(timeout=15.0) as tg_client, BCParksClient() as client:
        try:
            send_telegram(bot_token, chat_id, "campcli daemon started", client=tg_client)
        except Exception as e:
            _log(f"startup telegram failed: {e}")

        while True:
            try:
                bookings = store.list_bookings()
                blocked_ids = {b.park_id for b in store.list_blocked_parks()}
                _log(
                    f"poll start (bookings={len(bookings)}, blocked={len(blocked_ids)}, "
                    f"seen={len(seen)})"
                )

                def on_match(m: WeekendMatch) -> None:
                    key = (m.park_id, m.map_id, m.start_date, m.nights)
                    if key in seen:
                        return
                    if not filters.should_notify(
                        m, bookings=bookings, blocked_park_ids=blocked_ids
                    ):
                        seen.add(key)
                        return
                    prev_gap, next_gap = filters.gap_days_to_nearest(m.start_date, bookings)
                    text = format_match_message(
                        m, prev_gap_days=prev_gap, next_gap_days=next_gap
                    )
                    try:
                        send_telegram(bot_token, chat_id, text, client=tg_client)
                        _log(f"notified: {m.park_name} {m.map_name} {m.start_date}")
                    except Exception as e:
                        _log(f"telegram send failed: {e}")
                        return  # don't add to seen — retry next iteration
                    seen.add(key)

                run_search(client, profile, progress=lambda s: _log(s), on_match=on_match)
            except KeyboardInterrupt:
                _log("interrupted, exiting")
                return
            except Exception as e:
                _log(f"poll iteration failed: {e}")
                traceback.print_exc(file=sys.stderr)

            time.sleep(interval_secs)
