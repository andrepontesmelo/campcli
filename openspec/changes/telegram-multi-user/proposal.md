## Why

The Telegram bot is single-user: one `TELEGRAM_CHAT_ID` env var, one chat target, one global `/verbose` toggle. Multiple people can't interact with the bot or choose their own verbose settings. No command auto-complete or buttons in chat UI.

## What Changes

- **Multi-user auth**: `tg_allowed_ids` list in `profile.json`; only these Telegram user IDs can command the bot or receive alerts.
- **Broadcast alerts**: every authorized user receives `WeekendMatch` notifications in their last-seen chat.
- **Per-user verbose mode**: each user independently toggles `/verbose` on/off; state persists in Settings DB per `verbose:{tg_id}` key.
- **Telegram bot UX**: `setMyCommands` registers `/verbose` with auto-complete in chat UI; `/verbose` reply shows inline keyboard `[ON] [OFF]` buttons.
- **Drop** `TELEGRAM_CHAT_ID` env var; keep `TELEGRAM_BOT_TOKEN`.
- **Last-seen chat tracking**: Settings DB key `chat:{tg_id}` stores each user's most recent chat (works for private and group chats).
- **CLI `telegram` subcommand**: `allow <tg_id>`, `revoke <tg_id>`, `list` to manage `tg_allowed_ids` in profile.json.
- **BREAKING**: `Telegram.send(text)` → `Telegram.send_to(chat_id, text)`; `HttpxTelegram.__init__` drops `chat_id` param; `DaemonLog` takes verbose-chat set instead of single bool.

## Capabilities

### New Capabilities

- `telegram-multi-user`: Multi-user Telegram bot with authorized-IDs gate, per-user verbose toggle, inline-keyboard UX, and command auto-complete via Bot API. Replaces single-chat env-var model with profile-backed user list.

### Modified Capabilities

- `profile-config`: `profile.json` gains `tg_allowed_ids` field.

## Impact

- **Removed**: `TELEGRAM_CHAT_ID` env var usage, global `verbose` setting key
- **Modified**: `domain/ports.py` (Telegram Protocol signature, TelegramUpdate model), `infrastructure/telegram.py` (HttpxTelegram), `application/command_router.py` (auth + per-user verbose + keyboard routing), `application/poller.py` (multi-user command handling + broadcast), `application/daemon_log.py` (per-user verbose), `application/search_notifier.py` (multi-target notify), `application/profile.py` (tg_allowed_ids field), `composition/daemon.py` (drop chat_id wiring), `composition/cli.py` (drop chat_id check + new telegram subcommand)
- **New**: `application/telegram_users.py` (authorized user management domain logic)
- **Config**: `profile.json` gains `tg_allowed_ids` field; Settings DB gains `verbose:{tg_id}` and `chat:{tg_id}` keys
