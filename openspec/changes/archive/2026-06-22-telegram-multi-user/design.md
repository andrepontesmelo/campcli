## Context

Current state: Telegram bot is single-channel. `HttpxTelegram` holds one `chat_id` from `TELEGRAM_CHAT_ID` env var. `Telegram.send(text)` targets that single chat. `poll_updates()` filters by that chat_id. Global verbose toggle in Settings DB key `verbose`. CLI `daemon` command requires both `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`.

Goal: any number of authorized users can interact with the same bot instance. Each controls their own verbose. Alerts broadcast to all. Bot uses Telegram-native UI (auto-complete commands + inline keyboard).

Layers per ADR-0010: new `application/telegram_users.py` holds auth-domain logic. Composition root wires user state from profile + settings into Poller/DaemonLog/SearchNotifier.

## Goals / Non-Goals

**Goals:**
- Multiple authorized Telegram users in one daemon instance
- Per-user verbose toggle persisted in Settings DB
- Inline keyboard reply for `/verbose` command
- BotFather command registration (`setMyCommands`) on daemon start
- Broadcast WeekendMatch alerts to all authorized users
- Last-seen chat tracking (automatic, works for private and group chats)
- CLI subcommand `telegram allow|revoke|list` to manage profile.json `tg_allowed_ids`

**Non-Goals:**
- Multiple profiles — `tg_allowed_ids` in profile.json is a scaffold; daemon runs one profile
- Per-user notification preferences / per-user blocked parks / per-user watches
- Multi-daemon / multi-bot support
- Offline user management (CLI reads/writes profile.json directly)

## Decisions

### D1: `tg_allowed_ids` lives in `profile.json`, not Settings DB

Profile.json is the user-facing config file. Authorized IDs are configuration, not runtime state. `tg_allowed_ids: []` is a field in the Profile Pydantic model. CLI `telegram allow/revoke` reads the profile file, edits the list, and re-writes it — same pattern as hand-editing the JSON.

### D2: Per-user verbose state in Settings DB key `verbose:{tg_id}`

Per-user state that changes at runtime goes in Settings DB, per earlier design agreement (immutable config in JSON, mutable runtime state in DB). Global `verbose` key is removed.

### D3: Last-seen chat in Settings DB key `chat:{tg_id}`

Bot automatically learns each authorized user's chat_id from their first interaction. No setup. Works for both private chats (tg_id == chat_id) and groups (tg_id != chat_id). Alert broadcasts use last-known chat per user.

### D4: Telegram Protocol signature: `send_to(chat_id, text)` replaces `send(text)`

`HttpxTelegram.__init__` drops `chat_id` — token-only. Every send call explicitly names a chat. `poll_updates()` returns ALL unfiltered updates; the Poller filters by authorized user IDs. This keeps the adapter stateless about targets.

### D5: `TelegramUpdate` extends to support callback queries

Add optional `from_id`, `callback_query_id`, `callback_data` fields. The update type is determined by which fields are present (`text` → message command, `callback_query_id` → button press). Keep a single model, not a union — avoids breaking all consumers.

### D6: Inline keyboard via `send_inline_keyboard(chat_id, text, buttons)`

New Telegram Protocol method. Sends a message with `reply_markup` containing `InlineKeyboardMarkup`. The Poller handles callback query updates in the same `_handle_commands` tick: filters for `callback_query_id`, routes to a callback handler, calls `answer_callback_query` to dismiss the spinner.

### D7: `DaemonLog` accepts `verbose_chats: set[str]` instead of single `verbose: bool`

Per-user verbose means DaemonLog must route log lines to multiple chats. `set_verbose(chat_id, on)` adds/removes a chat from the set. `log(msg)` sends to all chats in the set. No user_id awareness — just chat_ids. The Poller maps user_id → chat_id via Settings DB.

### D8: `SearchNotifier.notify(match, *, chat_id)` — poller loops over targets

SearchNotifier remains stateless about users. The Poller iterates over authorized users' last-seen chats and calls `notify(match, chat_id=chat)` for each. The notification suppression (dedup, blocked, booking adjacency) still runs once per poll — `start_poll()` sets context once, `notify()` checks once, but the `send` is per-chat.

Wait — the current `NotificationPolicy.mark_sent()` records that a notification was sent. With broadcast, we should mark sent once (after all chats receive it), not once per chat. The Poller orchestrates: call `notify()` once to get the decision, then broadcast to all chats, then mark sent.

Actually, keep `SearchNotifier` as a per-notification sender. The Poller calls it in a loop. But the NotificationPolicy dedup must run once. So: `Notifier.notify()` returns the decision; the Poller broadcasts if not suppressed.

## Risks / Trade-offs

- **[Risk] Inline keyboard callback queries time out after 30s** → Answer immediately with no-op if processing takes long. Telegram sends callback queries that the bot must ACK quickly.
- **[Risk] Group chats: user A in group G toggles verbose** → Bot remembers chat_id=G for user A. All verbose output goes to group G, not user A's private chat. This is by design (last-seen).
- **[Trade-off] No per-user notification policy** → All authorized users see the same WeekendMatches. Same dedup state (one poll cycle, one memory). Acceptable until users diverge in preferences.
- **[Risk] user_ids must be manually obtained** → CLI `telegram allow 123456` requires the user to know their Telegram numeric ID. Mitigation: when an unauthorized user sends any message, bot replies "Your Telegram ID is NNN. Ask an admin to run `campcli telegram allow NNN`."

## Migration Plan

1. Add `tg_allowed_ids` to Profile model + default JSON
2. Extend Telegram Protocol + TelegramUpdate model
3. Refactor HttpxTelegram (drop chat_id, add multi-chat methods)
4. Add application/telegram_users.py (auth + user state management)
5. Refactor command_router (auth check, per-user verbose, callback handler)
6. Refactor Poller (multi-user updates, broadcast, per-user verbose routing)
7. Refactor DaemonLog (verbose_chats set)
8. Refactor SearchNotifier (per-chat notify)
9. Update daemon.py composition (drop chat_id)
10. Add CLI telegram subcommand
11. Update tests
12. Run full test suite + mypy

Rollback: re-add `TELEGRAM_CHAT_ID` env var check, revert Protocol signatures. Settings DB verbose keys can coexist with old global key. Profile.json `tg_allowed_ids` is backward-compatible (empty list → no auth → no notifications).

## Open Questions

(none — all resolved during interview)
