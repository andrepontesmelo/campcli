"""HttpxTelegram — sole Infrastructure adapter for the Telegram Protocol."""
from __future__ import annotations

import httpx

from ..domain.ports import Telegram, TelegramUpdate


TG_MAX_LEN = 4096


class HttpxTelegram:
    def __init__(
        self, token: str, chat_id: str, client: httpx.Client | None = None
    ) -> None:
        self._token = token
        self._chat_id = chat_id
        self._own_client = client is None
        self._client = client or httpx.Client(timeout=15.0)

    def close(self) -> None:
        if self._own_client:
            self._client.close()

    def __enter__(self) -> HttpxTelegram:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def send(self, text: str) -> None:
        url = f"https://api.telegram.org/bot{self._token}/sendMessage"
        for chunk in _chunks(text, TG_MAX_LEN):
            resp = self._client.post(
                url,
                json={
                    "chat_id": self._chat_id,
                    "text": chunk,
                    "disable_web_page_preview": False,
                },
            )
            resp.raise_for_status()

    def poll_updates(self, offset: int | None = None) -> list[TelegramUpdate]:
        url = f"https://api.telegram.org/bot{self._token}/getUpdates"
        params: dict[str, int] = {"timeout": 0}
        if offset is not None:
            params["offset"] = offset
        try:
            resp = self._client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            if not data.get("ok"):
                return []
            raw = data.get("result", [])
        except Exception:
            import sys
            print(f"telegram poll_updates failed", file=sys.stderr)
            return []
        out: list[TelegramUpdate] = []
        for upd in raw:
            uid = upd.get("update_id")
            if uid is None:
                continue
            msg = upd.get("message") or {}
            chat_id = str((msg.get("chat") or {}).get("id", ""))
            if chat_id != self._chat_id:
                continue
            out.append(
                TelegramUpdate(
                    update_id=uid,
                    chat_id=chat_id,
                    text=(msg.get("text") or "").strip(),
                )
            )
        return out


def _chunks(text: str, n: int):
    if len(text) <= n:
        yield text
        return
    for i in range(0, len(text), n):
        yield text[i : i + n]
