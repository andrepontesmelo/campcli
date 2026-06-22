## 1. Domain models and ports

- [ ] 1.1 Add `tg_allowed_ids: list[int]` field to `Profile` model in `application/profile.py`
- [ ] 1.2 Add `tg_allowed_ids: []` to `_DEFAULT_JSON` in `application/profile.py`
- [ ] 1.3 Extend `TelegramUpdate` model in `domain/ports.py`: add optional `from_id: int | None`, `callback_query_id: str | None`, `callback_data: str | None`
- [ ] 1.4 Add `BotCommand` model to `domain/ports.py`: `command: str`, `description: str`
- [ ] 1.5 Extend `Telegram` Protocol in `domain/ports.py`: replace `send(text)` with `send_to(chat_id, text)`, add `set_my_commands`, `send_inline_keyboard`, `edit_message_reply_markup`, `answer_callback_query`

## 2. HttpxTelegram adapter

- [ ] 2.1 Remove `chat_id` from `HttpxTelegram.__init__` (keep `token`)
- [ ] 2.2 Rename `send(text)` to `send_to(chat_id, text)`
- [ ] 2.3 Change `poll_updates()` to return ALL updates unfiltered by chat_id, include `from_id` from `message.from.id`, handle callback_query updates
- [ ] 2.4 Implement `set_my_commands(commands)` via `https://api.telegram.org/bot{token}/setMyCommands`
- [ ] 2.5 Implement `send_inline_keyboard(chat_id, text, buttons) -> int` via `sendMessage` with `reply_markup`; return `message_id` from response
- [ ] 2.6 Implement `edit_message_reply_markup(chat_id, message_id, text, buttons | None)` via `editMessageReplyMarkup` or `editMessageText`
- [ ] 2.7 Implement `answer_callback_query(query_id, text)` via `answerCallbackQuery`

## 3. Application — authorized user management

- [ ] 3.1 Create `application/telegram_users.py` with `is_authorized(tg_id: int, allowed_ids: list[int]) -> bool`
- [ ] 3.2 Add `unauthorized_reply(tg_id: int) -> str` returning the ID-revealing message
- [ ] 3.3 Add helper `build_verbose_chat_set(settings_repo, allowed_ids) -> set[str]` that reads `verbose:{tg_id}` and `chat:{tg_id}` from settings

## 4. Application — command router

- [ ] 4.1 Change `dispatch(text, poller)` to `dispatch(update: TelegramUpdate, poller) -> str | None` accepting the full update
- [ ] 4.2 Add auth gate: if `update.from_id` not in `tg_allowed_ids`, return unauthorized reply; skip auth when `tg_allowed_ids` is empty
- [ ] 4.3 Change `/verbose on` and `/verbose off` text handlers to per-user: store `verbose:{tg_id}` instead of global key
- [ ] 4.4 Add `/verbose` (bare) handler: reply with inline keyboard showing current verbose state
- [ ] 4.5 Add callback query dispatch: `callback_data` values `verbose_on`, `verbose_off` → toggle per-user verbose, return edit-message instruction
- [ ] 4.6 Define `COMMANDS` list for `setMyCommands` registration: `[{"command": "verbose", "description": "Toggle verbose daemon logging"}]`

## 5. Application — Poller

- [ ] 5.1 Load `tg_allowed_ids` from profile, store in Poller
- [ ] 5.2 Remove global verbose read from `__init__`; replace with `_refresh_verbose_chats()` that builds set from per-user settings
- [ ] 5.3 Change `set_verbose(on: bool)` to `set_verbose(tg_id: int, on: bool, chat_id: str | None = None)` — update settings, refresh chat set
- [ ] 5.4 Update `_handle_commands()`: pass full TelegramUpdate to dispatch, handle auth rejections, handle callback query edit-message responses
- [ ] 5.5 On each update, store `chat:{tg_id}` in settings (last-seen tracking)
- [ ] 5.6 In `start()`, call `telegram.set_my_commands()` with registered commands
- [ ] 5.7 In `tick()`, pass `chat_ids` list (last-seen chats of all authorized users) to `SearchNotifier.notify()`
- [ ] 5.8 Handle callback queries: parse `callback_query_id` and `callback_data`, call relevant handler, answer callback query

## 6. Application — DaemonLog

- [ ] 6.1 Change `__init__` to accept `verbose_chats: set[str]` instead of `verbose: bool`
- [ ] 6.2 Change `set_verbose(on: bool)` to `set_verbose(chat_id: str, on: bool)`
- [ ] 6.3 Change `log(msg)` to send to all chats in `_verbose_chats` (in addition to stderr)
- [ ] 6.4 Keep `__call__` alias

## 7. Application — SearchNotifier

- [ ] 7.1 Change `notify(match: WeekendMatch)` to `notify(match: WeekendMatch, *, chat_ids: list[str])`
- [ ] 7.2 After rendering the message, send to all `chat_ids` via `telegram.send_to()`, catching per-chat errors
- [ ] 7.3 Call `mark_sent()` once after all sends (or on first successful send; skip if all fail)

## 8. Composition — daemon.py

- [ ] 8.1 Remove `chat_id` parameter from `run_forever()`
- [ ] 8.2 Remove `chat_id` from `HttpxTelegram` construction (pass only `bot_token`)
- [ ] 8.3 Create `DaemonLog` with initial empty verbose_chats set; refresh after Poller is constructed
- [ ] 8.4 Remove `SearchNotifier` `rest_days` drop-in from `run_forever` (already handled in poller)

## 9. CLI — telegram subcommand + daemon changes

- [ ] 9.1 Create `telegram_app = typer.Typer()` in `cli.py` with `no_args_is_help=True`
- [ ] 9.2 Add `telegram allow <tg_id> [<tg_id> ...]`: read profile.json, add IDs, write back, confirm
- [ ] 9.3 Add `telegram revoke <tg_id> [<tg_id> ...]`: read profile.json, remove IDs, write back, confirm
- [ ] 9.4 Add `telegram list`: read profile.json, display tg_allowed_ids
- [ ] 9.5 Register `app.add_typer(telegram_app, name="telegram")`
- [ ] 9.6 Remove `TELEGRAM_CHAT_ID` requirement from `daemon_cmd()` (keep only `TELEGRAM_BOT_TOKEN`)
- [ ] 9.7 Remove `chat_id` parameter from `daemon_svc.run_forever()` call

## 10. Update existing tests

- [ ] 10.1 Update `test_telegram.py` for new HttpxTelegram signature (no chat_id, send_to, poll_updates unfiltered)
- [ ] 10.2 Update `test_poller.py` for new Poller signature (no global verbose, tg_allowed_ids, per-user routing)
- [ ] 10.3 Update `test_search_notifier.py` for `notify()` with `chat_ids` parameter
- [ ] 10.4 Update `test_notification_policy.py` for broadcast semantics (mark_sent once)
- [ ] 10.5 Update `test_daemon_log.py` for verbose_chats set

## 11. New tests

- [ ] 11.1 Add test for auth rejection (unauthorized user gets ID-revealing message)
- [ ] 11.2 Add test for per-user verbose toggle via callback query
- [ ] 11.3 Add test for inline keyboard reply to /verbose
- [ ] 11.4 Add test for broadcast: WeekendMatch sent to all authorized chats
- [ ] 11.5 Add test for last-seen chat tracking update
- [ ] 11.6 Add test for CLI telegram allow/revoke/list
- [ ] 11.7 Add test for empty tg_allowed_ids → no alerts, no command processing
- [ ] 11.8 Add test for HttpxTelegram multi-chat: send_to, set_my_commands, inline_keyboard, callback_query parsing

## 12. Type checking and final validation

- [ ] 12.1 Run `mypy src/campcli` and fix all type errors
- [ ] 12.2 Run `pytest` full suite, ensure all tests pass
- [ ] 12.3 Verify `openspec validate telegram-multi-user --strict` passes
