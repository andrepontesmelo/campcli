"""HttpxTelegram — sole Infrastructure adapter for the Telegram Protocol."""
from __future__ import annotations

import httpx

from ..domain.ports import BotCommand, TelegramUpdate


TG_MAX_LEN = 4096


class HttpxTelegram:
    def __init__(
        self, token: str, client: httpx.Client | None = None
    ) -> None:
        self._token = token
        self._own_client = client is None
        self._client = client or httpx.Client(timeout=15.0)

    def close(self) -> None:
        if self._own_client:
            self._client.close()

    def __enter__(self) -> HttpxTelegram:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def send_to(self, chat_id: str, text: str) -> int:
        url = f"https://api.telegram.org/bot{self._token}/sendMessage"
        last_id = 0
        for chunk in _chunks(text, TG_MAX_LEN):
            resp = self._client.post(
                url,
                json={
                    "chat_id": chat_id,
                    "text": chunk,
                    "disable_web_page_preview": False,
                },
            )
            resp.raise_for_status()
            last_id = resp.json()["result"]["message_id"]
        return last_id

    def poll_updates(
        self, offset: int | None = None, long_poll_timeout: int = 0
    ) -> list[TelegramUpdate]:
        url = f"https://api.telegram.org/bot{self._token}/getUpdates"
        params: dict[str, int] = {"timeout": long_poll_timeout}
        if offset is not None:
            params["offset"] = offset
        request_timeout = long_poll_timeout + 10 if long_poll_timeout else None
        try:
            resp = self._client.get(url, params=params, timeout=request_timeout)
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
            from_id = (msg.get("from") or {}).get("id")
            text = (msg.get("text") or "").strip()
            reply_to = msg.get("reply_to_message")
            reply_to_message_id = (
                reply_to.get("message_id") if isinstance(reply_to, dict) else None
            ) if reply_to else None
            # Handle callback queries
            cb = upd.get("callback_query") or {}
            from_id = from_id or (cb.get("from") or {}).get("id")
            cb_id = cb.get("id")
            cb_data = cb.get("data")
            cb_msg_id = None
            if cb_id:
                cb_msg = cb.get("message") or {}
                chat_id = str((cb_msg.get("chat") or {}).get("id", chat_id))
                cb_msg_id = cb_msg.get("message_id")
            out.append(
                TelegramUpdate(
                    update_id=uid,
                    chat_id=chat_id,
                    text=text,
                    from_id=from_id,
                    callback_query_id=cb_id,
                    callback_data=cb_data,
                    message_id=cb_msg_id,
                    reply_to_message_id=reply_to_message_id,
                )
            )
        return out

    def set_my_commands(self, commands: list[BotCommand]) -> None:
        url = f"https://api.telegram.org/bot{self._token}/setMyCommands"
        payload = {
            "commands": [
                {"command": c.command, "description": c.description}
                for c in commands
            ]
        }
        resp = self._client.post(url, json=payload)
        resp.raise_for_status()

    def send_inline_keyboard(
        self, chat_id: str, text: str, buttons: list[list[dict[str, str]]]
    ) -> int:
        url = f"https://api.telegram.org/bot{self._token}/sendMessage"
        resp = self._client.post(
            url,
            json={
                "chat_id": chat_id,
                "text": text,
                "reply_markup": {"inline_keyboard": buttons},
            },
        )
        resp.raise_for_status()
        return resp.json()["result"]["message_id"]

    def edit_message_reply_markup(
        self,
        chat_id: str,
        message_id: int,
        text: str | None = None,
        buttons: list[list[dict[str, str]]] | None = None,
    ) -> None:
        payload: dict[str, object] = {
            "chat_id": chat_id,
            "message_id": message_id,
        }
        if text is not None:
            # Changing text — use editMessageText
            payload["text"] = text
            if buttons is not None:
                payload["reply_markup"] = {"inline_keyboard": buttons}
            url = f"https://api.telegram.org/bot{self._token}/editMessageText"
        else:
            # Only changing reply markup
            if buttons is not None:
                payload["reply_markup"] = {"inline_keyboard": buttons}
            url = f"https://api.telegram.org/bot{self._token}/editMessageReplyMarkup"
        resp = self._client.post(url, json=payload)
        resp.raise_for_status()

    def answer_callback_query(self, query_id: str, text: str | None = None) -> None:
        url = f"https://api.telegram.org/bot{self._token}/answerCallbackQuery"
        payload: dict[str, str] = {"callback_query_id": query_id}
        if text is not None:
            payload["text"] = text
        resp = self._client.post(url, json=payload)
        resp.raise_for_status()


def _chunks(text: str, n: int):
    if len(text) <= n:
        yield text
        return
    for i in range(0, len(text), n):
        yield text[i : i + n]
