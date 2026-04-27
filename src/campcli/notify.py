"""Telegram notifier + per-match message formatter."""
from __future__ import annotations

import httpx

from .booking import quote_url
from .drive_times import load_cache as load_drive_cache
from .models import WeekendMatch

TG_MAX_LEN = 4096


def send_telegram(
    token: str,
    chat_id: str,
    text: str,
    *,
    client: httpx.Client | None = None,
) -> None:
    """POST text to Telegram. Splits messages >4096 chars."""
    own_client = client is None
    c = client or httpx.Client(timeout=15.0)
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        for chunk in _chunks(text, TG_MAX_LEN):
            resp = c.post(
                url,
                json={
                    "chat_id": chat_id,
                    "text": chunk,
                    "disable_web_page_preview": False,
                },
            )
            resp.raise_for_status()
    finally:
        if own_client:
            c.close()


def fetch_updates(
    token: str,
    offset: int | None = None,
    *,
    client: httpx.Client | None = None,
) -> list[dict]:
    """Short-poll Telegram for incoming updates (timeout=0). Returns [] on any error."""
    own_client = client is None
    c = client or httpx.Client(timeout=15.0)
    try:
        url = f"https://api.telegram.org/bot{token}/getUpdates"
        params: dict[str, int] = {"timeout": 0}
        if offset is not None:
            params["offset"] = offset
        resp = c.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
        if not data.get("ok"):
            return []
        return data.get("result", [])
    except Exception:
        return []
    finally:
        if own_client:
            c.close()


def _chunks(text: str, n: int):
    if len(text) <= n:
        yield text
        return
    for i in range(0, len(text), n):
        yield text[i : i + n]


def _weeks_label(days: int | None, suffix: str) -> str:
    if days is None:
        return f"  no booking {suffix}"
    if days == 0:
        return f"  same day as a booking ({suffix})"
    weeks = days / 7.0
    if weeks >= 1:
        return f"  {weeks:.1f} weeks {suffix}"
    return f"  {days} days {suffix}"


def format_match_message(
    m: WeekendMatch,
    *,
    prev_gap_days: int | None,
    next_gap_days: int | None,
) -> str:
    drive = load_drive_cache().get(m.park_id, {}).get("hours")
    drive_str = f"  ({drive:.1f}h)" if drive is not None else ""
    fee = f"${m.fee_per_night:.0f}/night" if m.fee_per_night is not None else "$?/night"
    spots = "spot" if m.available_count == 1 else "spots"
    url = quote_url(park_id=m.park_id, map_id=m.map_id, start=m.start_date, nights=m.nights)
    lines = [
        f"🏕  {m.park_name}{drive_str}",
        f"   {m.map_name}",
        f"   {m.start_date.strftime('%a %b %d')} → {m.end_date.strftime('%a %b %d')}  ({m.nights}n)  {fee}",
        f"   {m.available_count} {spots}",
        _weeks_label(prev_gap_days, "before nearest booking"),
        _weeks_label(next_gap_days, "after nearest booking"),
        f"   {url}",
    ]
    return "\n".join(lines)
