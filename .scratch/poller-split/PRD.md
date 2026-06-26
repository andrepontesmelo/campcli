# PRD: Split Poller Into Search Loop, Command Responses, and Telegram Settings

## Problem Statement

`application/poller.py` is a 398-line single-class module that mixes three distinct concerns: the availability polling search loop, Telegram command dispatch and response handling, and Telegram user settings management (verbose mode, chat_id tracking). ADR-0005 requires use-case functions grouped by Domain noun — the Poller class bundles search, commands, and settings under one roof. Adding a new Telegram bot command or adjusting the poll loop requires navigating a 398-line file where responsibilities bleed into each other. Testing any one concern requires instantiating the full Poller with its 8 dependencies.

## Solution

Split `poller.py` into three focused application modules — search loop, command responses, and Telegram settings — each with module-level functions (not classes per ADR-0005). The composition root (daemon.py) wires them together instead of wiring one monolithic Poller.

## User Stories

1. As a developer, I want to understand the availability polling loop by reading one focused module, so that I can reason about search behavior without scrolling past command dispatch code.
2. As a developer, I want to add a new Telegram bot command by editing only the command responses module, so that I don't risk breaking the search loop.
3. As a developer, I want to test the search loop in isolation with just the ports it needs, so that search tests don't need Telegram or settings dependencies.
4. As a developer, I want to test command response handling with a fake Telegram adapter, so that bot command tests are fast and deterministic.
5. As a developer, I want test verbose-mode toggling without instantiating a Poller, so that settings tests are focused.
6. As a code reviewer, I want to see a single-responsibility module for each concern, so that I can review changes to one domain without reviewing unrelated code.
7. As a developer debugging a poll loop issue, I want to trace the search flow through a linear function without jumping between loop logic and command handling.

## Implementation Decisions

### Module split

1. **`application/search_loop.py`** — The core availability polling loop:
   - `run_search_once(api, profile_repo, settings_repo, drive_times, not_interested_repo, notifier_factory, log_fn, clock) -> None`
   - Accepts all ports as function arguments (no `self`).
   - Contains: profile loading, park/map resolution, availability checking, match detection, notification dispatch.
   - Internal helpers can be private module-level functions.

2. **`application/command_responses.py`** — Telegram update processing:
   - `process_update(upd, telegram, settings_repo, allowed_ids, log_fn) -> None`
   - `handle_commands_forever(telegram, settings_repo, allowed_ids, log_fn, stop_event) -> None`
   - Relies on existing `application/command_router.dispatch()` for routing — this module handles the response side (send reply, inline keyboard, callback answer).

3. **`application/telegram_settings.py`** — Telegram user settings management:
   - `get_verbose(settings_repo, tg_id) -> bool`
   - `set_verbose(settings_repo, tg_id, enabled, chat_id) -> None`
   - `get_chat_id(settings_repo, tg_id) -> str | None`
   - `set_chat_id(settings_repo, tg_id, chat_id) -> None`
   - `refresh_tg_allowed_ids(profile_repo) -> list[int]`
   - `build_verbose_chats(settings_repo, allowed_ids) -> set[str]`

### What happens to poller.py?

`poller.py` is deleted after extraction. The `Poller` class is dissolved. `composition/daemon.py` wires the three modules together with shared dependencies.

### What stays in composition/daemon.py

- Creating the shared logger (`DaemonLog`)
- Creating the shared notifier factory
- Wiring: `run_search_once(...)`, `handle_commands_forever(...)`, telegram settings functions
- The threading loop and start/stop coordination

### Per-profile notifier cache

Currently `self._notifiers: dict[int, SearchNotifier]` lives on the Poller instance. After split: this cache moves to `composition/daemon.py` as module-level state or a simple dict in the daemon's scope. The notifier factory pattern remains — `search_loop.run_search_once()` receives a `Callable[[int], SearchNotifier]` factory.

### Command routing change

`handle_one_command_batch(poller)` is already extracted as a module-level function. After split, it becomes `handle_one_command_batch(telegram, settings_repo, allowed_ids, log_fn)` — no Poller reference needed.

### Naming note

The grilling analysis identified that "TelegramSettings value object" was imprecise. These are application service functions operating on `SettingsRepo`, not a value object. The module is named `telegram_settings.py` to match the `telegram_users.py` pattern.

## Testing Decisions

### What makes a good test

Each module is tested in isolation with duck-typed fake implementations of the ports. Tests verify external behavior: for `search_loop`, that the right profiles are loaded, availability is queried, and notifier is called; for `command_responses`, that the right Telegram methods are called for each dispatch result type; for `telegram_settings`, that settings are read/written correctly.

### Prior art

- `tests/test_poller.py` — existing Poller tests. Will be restructured into three test files matching the three new modules.
- `tests/test_command_router.py` — already tests `dispatch()` in isolation; `command_responses.py` tests will be the response-side counterpart.
- `tests/test_telegram_users.py` — similar pattern (settings management functions with SettingsRepo).

### Modules tested

- `application/search_loop.py` — `tests/test_search_loop.py`
- `application/command_responses.py` — `tests/test_command_responses.py`  
- `application/telegram_settings.py` — `tests/test_telegram_settings.py`

## Out of Scope

- Changing the polling algorithm or availability check logic
- Extracting `notification_policy.py` further (already a separate module)
- Extracting `command_router.py` further (already a separate module)
- Changing CLI behavior (cli.py is not touched)
- Adding new Telegram bot commands

## Further Notes

- The Poller's `start()` method (setMyCommands + startup notification) is wiring/coordination code. It moves to `composition/daemon.py` as the entry point, not to any application module.
- `_refresh_verbose_chats` currently calls `build_verbose_chat_set` from `telegram_users.py`. After split, this call is in `telegram_settings.py` or kept in daemon.py depending on whether it's pure coordination or settings logic.
- `_refresh_tg_allowed_ids` is pure profile querying — it belongs in `telegram_settings.py` alongside the other user management functions.
- The `_notifiers` cache dict doesn't need to be a class attribute — daemon.py manages it as part of the loop coordination.
