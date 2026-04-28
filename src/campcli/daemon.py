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
from .notify import fetch_updates, format_match_message, send_telegram
from .search import run as run_search
from .store import get_setting, set_setting


def run_forever(
    *,
    bot_token: str,
    chat_id: str,
    interval_secs: float = 1.0,
    profile: dict | None = None,
) -> None:
    profile = profile or DEFAULT_PROFILE
    seen: set[tuple[int, int, date, int]] = set()
    update_offset: int | None = None
    verbose_enabled = get_setting("verbose") == "on"

    def _log(msg: str) -> None:
        line = f"[{datetime.now().isoformat(timespec='seconds')}] {msg}"
        print(line, file=sys.stderr, flush=True)
        if verbose_enabled:
            try:
                send_telegram(bot_token, chat_id, line, client=tg_client)
            except Exception:
                pass

    with httpx.Client(timeout=15.0) as tg_client, BCParksClient() as client:
        try:
            send_telegram(bot_token, chat_id, "campcli daemon started v3", client=tg_client)
        except Exception as e:
            _log(f"startup telegram failed: {e}")

        if verbose_enabled:
            _log("verbose logging is ON")

        while True:
            try:
                # Poll for incoming Telegram commands.
                updates = fetch_updates(bot_token, update_offset, client=tg_client)
                for upd in updates:
                    uid = upd.get("update_id")
                    if uid is not None:
                        update_offset = uid + 1
                    msg = upd.get("message") or {}
                    sender_chat = str((msg.get("chat") or {}).get("id", ""))
                    if sender_chat != chat_id:
                        continue
                    text = (msg.get("text") or "").strip()
                    _log(f"received command: {text!r}")
                    if text == "/verbose on":
                        set_setting("verbose", "on")
                        verbose_enabled = True
                        send_telegram(
                            bot_token, chat_id, "verbose logging ON", client=tg_client,
                        )
                    elif text == "/verbose off":
                        set_setting("verbose", "off")
                        verbose_enabled = False
                        send_telegram(
                            bot_token, chat_id, "verbose logging OFF", client=tg_client,
                        )

                # Check availability.
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
