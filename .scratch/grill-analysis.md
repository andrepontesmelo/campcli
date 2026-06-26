# Grill Analysis — 2026-06-25

Autonomous grilling of 3 features against existing ADRs and glossary.

## Feature 1: `[L] cli-use-case-extract`

**Summary**: Extract ~400 LoC of use-case logic from `composition/cli.py` (882 lines, 38 functions, 4 Typer-wired) into `application/cli_profile.py` and `application/cli_search.py`.

**ADR Stress-Test**:
- ✅ **ADR-0002/0010** (composition root limited to wiring): `cli.py` currently has ~33 helper functions beyond the 4 Typer commands. These helpers do profile CRUD, search, not_interested management — pure use-case logic that shouldn't live in the composition layer.
- ✅ **ADR-0005** (grouped by domain noun): The split into `cli_profile` and `cli_search` follows the existing pattern (`application/search.py`, `application/poller.py`).
- ⚠️ **Naming concern**: `cli_profile.py` and `cli_search.py` prefix with "cli_" — but the extracted modules are application-layer use cases, not CLI-specific. The "cli_" prefix is misleading. Better names: `application/profile_use_cases.py` and `application/search_use_cases.py`, or merge into existing modules (`application/search.py` already exists — would it bloat?).
- ✅ **ADR-0001** (Application depends on Protocols): The extracted functions will still receive Protocol-typed dependencies. No violation.

**Terminology Check**:
- "use-case logic" vs "wiring": Clear boundary. Use-case = business orchestration (resolving parks, building queries, running searches). Wiring = constructing adapters (`BCParksClient(...)`, `HttpxTelegram(...)`) and decorating with `@app.command(...)`.

**Edge Cases**:
- `_run_profile_migration` (L132): This is infrastructure-level migration logic, not a use case. It calls the concrete store. Should stay in composition or move to `application/migrate_profile.py` (which already exists).
- `_store` (L91): Concrete adapter construction — MUST stay in composition root.
- `api_call` (L99): Wraps `BCParksClient` — concrete adapter reference — MUST stay in composition.
- `resolve_profile` (L146): Resolves profile name → Profile object from repo. This IS use-case logic. Should be extracted.

**Decision**: Extract. Naming: drop "cli_" prefix — use `application/profile_commands.py` and merge search-related into existing `application/search.py` where possible. `_run_profile_migration` stays in composition or joins `application/migrate_profile.py`.

**ADR warranted?** No. This is enforcement of existing ADRs, not a new decision.

---

## Feature 2: `[XS] walk-in-predicate-extract`

Already validated. No grilling needed (XS size). Confirmed: exact duplication at `search.py:188` and `poller.py:143`. Target: `application/catalog.py` as `is_bookable_map(m: Map) -> bool`.

---

## Feature 3: `[M] poller-split`

**Summary**: Split `application/poller.py` (398 lines, 13 functions, 1 class) into search use case, command dispatch, and TelegramSettings value object.

**ADR Stress-Test**:
- ✅ **ADR-0005** (group by domain noun): Current `Poller` class mixes 3 concerns: search (`run_search_once`), command routing (`_process_update`, `handle_commands_forever`), and Telegram settings management (`set_verbose`, `_get_verbose`, `_refresh_verbose_chats`, `_get_chat_id_for_user`). These are different domain nouns.
- ✅ **ADR-0001** (Protocols): No concrete adapter imports currently exist. Extraction won't introduce any.
- ⚠️ **Module naming**: "TelegramSettings value object" is imprecise per CONTEXT.md. The settings-related code in Poller manages `verbose` flags and `chat_id` tracking in SettingsRepo. It's NOT a value object — it's a settings coordinator. Better name: `application/telegram_settings.py` with functions like `get_verbose(poller, tg_id)`, `set_verbose(poller, tg_id, on)`, `get_chat_id(poller, tg_id)` — functions operating on SettingsRepo, not a mutable object.
- ⚠️ **Command dispatch relationship**: `command_router.py` already exists in application/ and handles `dispatch(update, poller, allowed_ids)`. The `_process_update` method on Poller is the response side — it takes the router's output and sends Telegram messages. This is poller-specific wiring, not a separate use case. Could just thin it and keep it in the same file.

**Terminology Check**:
- "TelegramSettings value object" violates CONTEXT.md — no such concept exists. A "value object" is read-only (like DriveTimes). Settings management has side effects (writes to SettingsRepo). It's an application service, not a value object.
- "Command dispatch" overloads — `application/command_router.py` already handles command dispatch (routing). The remaining `_process_update` code is "command response handling."

**Revised module targets**:
1. `application/search_loop.py` — `run_search_once` as a module-level function (following ADR-0005: functions, not classes)
2. `application/telegram_settings.py` — verbose + chat_id management functions
3. Keep `_process_update` lean in `application/poller.py` alongside `handle_commands_forever` — or move to `application/command_responses.py`

**Decision**: Split. Naming: `search_loop.py`, `telegram_settings.py`. Keep command handling in poller or extract to `command_responses.py`.

**ADR warranted?** No. Follows existing ADRs.

---

## Feature 4: `[S] drivetimes-domain-move`

**Summary**: Move DriveTimes value object from `application/drive_times.py` to `domain/models.py`. Move `DEFAULT_REQUEST_INTERVAL_SECS` to `constants.py`. Thin `application/throttle.py`.

**ADR Stress-Test**:
- ✅ **Clean Architecture**: `DriveTimes` is a pure value object — no side effects, no I/O, read-only. By Clean Architecture, value objects belong in Domain, not Application. ADR-0010 listed it under `application/` as an artifact of the original flat structure, but the class itself has no application-layer coupling.
- ✅ **ADR-0010 amendment**: The move corrects the module listing in ADR-0010 without violating it. `domain/models.py` already contains Park, Map, AvailableSite, WeekendMatch — all DTOs/value objects. DriveTimes fits naturally alongside them.
- ⚠️ **Imports impact**: `DriveTimes` is consumed by 12+ callers (per hotspots: `hours_for` has fan-in 12). Moving it will update imports in `application/search.py`, `application/search_notifier.py`, `application/poller.py`, `composition/cli.py`, `composition/daemon.py`, and tests. The import path changes from `campcli.application.drive_times` to `campcli.domain.models`.
- ✅ **`DEFAULT_REQUEST_INTERVAL_SECS` → `constants.py`**: ADR-0010 says `constants.py` stays at the top level (shared by all layers). Currently this constant lives in `application/throttle.py` — incorrect layer. Moving to `constants.py` follows the rule.
- ⚠️ **What happens to `application/throttle.py`?** After moving `DEFAULT_REQUEST_INTERVAL_SECS` out, only `read_request_interval()` remains. The file becomes a thin module with one function. Could be merged into `application/poller.py` (its only caller?) or kept as-is for clarity. Recommendation: keep `throttle.py` with `read_request_interval()` — it's a clean seam.

**Glossary Check**:
- CONTEXT.md defines DriveTimes as "A read-only value object over geocoded driving durations from home to each Park; the seam for drive-time data. Application and Presentation receive it instead of reading the JSON cache." The definition already says "value object" — domain is the correct home.

**Decision**: Move. `DriveTimes` → `domain/models.py`. `DEFAULT_REQUEST_INTERVAL_SECS` → `constants.py`. Keep `throttle.py` as `read_request_interval()`.

**ADR warranted?** No — this is a corrective move, not a new trade-off decision.

---

## Feature 5: `[XS] search-notifier-presentation-leak`

Already validated. No grilling needed (XS size). Confirmed: `search_notifier.py` imports `render_match_message` from `presentation/format.py` — violates ADR-0010 layer dependency rule (application → presentation is OUTWARD). Fix: inject as `Callable` matching existing `log: Callable[..., None]` pattern.

---

## Cross-Cutting Notes

- All 5 features are refactoring tasks — no behavior changes, no API changes.
- Test impacts: import path updates only (layer-aware imports already exist, no restructuring).
- Merge order: #2 (walk-in predicate) and #5 (presentation leak) should go first as they're small and reduce noise in #1 and #3.
- #4 (DriveTimes move) should go before #1 and #3 to avoid merge conflicts on import paths.
