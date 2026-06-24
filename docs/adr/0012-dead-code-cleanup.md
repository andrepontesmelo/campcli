# campcli — Dead Code & Yagni Cleanup Refactor Plan

## Problem Statement

campcli's `src/` (~7974 LoC) has accumulated cruft during rapid iteration:

- A legacy `requirements.txt` lists 24 packages (camply, pandas, numpy, requests, rich,
  click, fake-useragent, tenacity, ratelimit, pydantic 1.x, six, python-dotenv, etc.)
  that **none of the current `src/` code imports**. `pyproject.toml` already declares
  the real runtime deps (`httpx`, `typer`, `pydantic`). `requirements.txt` is dead.
- `application/profile.py` is a 9-line stub whose own docstring says it will be deleted
  in a future cleanup pass. Per `.dex/archive.jsonl` (slice `hb19863q`, commit `dfbb679`)
  it was intentionally left as an import shim. There are no remaining importers.
- `BCParksApi.resource_details` implementation in `infrastructure/api.py` is unused —
  no production caller in `src/`. (The Protocol method must stay because test mocks
  declare it; the `api.py` implementation can go.)
- `Poller.tick()` exists as a single-iteration variant of `handle_commands_forever()`.
  Production uses `handle_commands_forever` only. `tick` is called **only** by tests;
  those tests can be rewired to call `handle_commands_forever` for one iteration, or to
  exercise the dedup/search path directly without `tick`.
- `SqliteStore.update` (store.py:229–258, ~30 lines) is implemented but never invoked;
  callers use `create`/`list`/`delete`/`set_enabled`.
- `_run_profile_migration()` is called from 18 separate CLI commands. The migration is
  idempotent and only does work once, but the boilerplate pollutes every command.

Total estimated cut: **~60 LoC of genuinely-dead code** plus 24 phantom dependencies.
Yagni items (Telegram bot menu, `command_router` two-level dispatch, poller dedup
helpers, `pricing.py` seasonal estimate) are noted but kept **out of scope** for this
pass — they are tested, used, and not strictly dead. This plan is conservative: only
items confirmed by grep to have zero callers AND zero meaningful tests get touched.

## Out of Scope

The following were considered and intentionally excluded:

- **`BotCommand` / `set_my_commands` / `BOT_COMMANDS`** — Has a passing test
  (`tests/test_telegram.py:176 test_set_my_commands`) and a conftest mock. Even though
  only one command ("verbose") is registered, the infrastructure is exercised.
- **`command_router.py` `COMMANDS` / `CB_HANDLERS` two-level dispatch** — All four
  commands (`/verbose`, `/verbose on`, `/verbose off`, `/not-interested`) are tested
  via `tests/test_command_router.py`. Reworking the dispatch dict adds risk without
  removing dead code.
- **`Poller._handle_commands` body / dedup state helpers** — Used by both `tick` and
  `handle_commands_forever`. Tests exercise the dedup behavior.
- **`application/pricing.py` `fee_per_night`** — Used by both `application/search.py`
  and `application/poller.py` for notification cards; rendered in
  `presentation/format.py`. Not dead — it's a documented FALLBACK for the missing
  live pricing endpoint.
- **`application/availability.py` / `AvailableSite`** — Used by `application/search.py`
  (`check_map`), `application/poller.py` (`check_map_from_data`), `presentation/format.py`
  (`render_available`, `render_available_list`), and `tests/test_availability.py`. Not
  dead.
- **`HttpxTelegram._chunks` / `TG_MAX_LEN`** — `tests/test_telegram.py:220
  test_long_message_chunked` exercises a 5000-char message and asserts 2 POSTs. Live
  defensive code, kept.
- **`holidays.py`, `_parse_hours`, `_pattern_to_raw`** — Small, used, not over-engineered.
- **`MANIFEST.drive_times_cache.MANUAL_LATLON`**, **`RateLimited`**,
  **`_refresh_verbose_chats`** — Each has at least one legitimate purpose.

## Solution

Six small, atomic commits. Each leaves the test suite green (`uv run pytest`). The
plan deliberately does not touch any symbol that is referenced from `tests/`, `src/`,
or `.dex/archive.jsonl` (decision records).

## Commits

### Commit 1 — Delete `application/profile.py`

- File: `src/campcli/application/profile.py` (9 lines including docstring).
- Verify zero importers: `rg -n "application\.profile" src/ tests/` returns no matches.
- Action: `git rm src/campcli/application/profile.py`.
- Verification: `uv run pytest` — full suite green; the file's only re-exports
  (`PatternSpec`, `parse_pattern`) come from `domain.models`, already imported
  wherever needed.
- Risk: none. The stub docstring says this deletion is expected.

### Commit 2 — Delete `requirements.txt`

- File: `requirements.txt` (24 lines, 24 packages).
- Verify zero references outside the file itself:
  `rg -n "requirements\.txt" --hidden -g '!.git' -g '!requirements.txt'` is empty.
- Verify zero imports of those packages from `src/`:
  - `rg -n "import camply|from camply"` — empty
  - `rg -n "import pandas|from pandas"` — empty
  - `rg -n "import numpy|from numpy"` — empty
  - `rg -n "import requests|from requests"` — empty
  - `rg -n "import rich|from rich"` — empty
  - `rg -n "import click|from click"` — empty
  - `rg -n "import tenacity|from tenacity"` — empty
  - `rg -n "import ratelimit|from ratelimit"` — empty
  - `rg -n "import fake_useragent|from fake_useragent"` — empty
  - (Spot-check pydantic 1.x: only `pydantic>=2` is in `pyproject.toml`; no `pydantic1`
    imports.)
- Action: `git rm requirements.txt`.
- Verification: `uv run pytest` — no change in behavior; `uv sync` continues to work
  from `pyproject.toml`.
- Note: there are no `.github/workflows/` files referencing pip+requirements.txt,
  so CI is unaffected. If a user has a manual `pip install -r requirements.txt`
  workflow documented elsewhere, it will need to be updated to `pip install .` or
  `uv sync`.

### Commit 3 — Delete `BCParksApi.resource_details` implementation in `api.py`

- File: `src/campcli/infrastructure/api.py` lines 127–131 (5 lines).
- Verify zero callers in `src/`:
  `rg -n "resource_details" src/` — only the definition itself.
- Verify Protocol method remains required:
  `rg -n "resource_details" tests/` — 5 references in `tests/conftest.py`,
  `tests/test_search.py`, `tests/test_availability.py` (2x). All are Protocol mocks.
- Action: remove `resource_details` from `api.py`. Keep the Protocol declaration in
  `domain/ports.py` (test mocks inherit from it). Add a one-line `# Protocol
  requirement, no implementation needed in current codepaths` comment in `api.py`.
- Verification: `uv run pytest` — full suite green. The Protocol method is abstract;
  tests provide concrete `FakeBCParksApi` implementations.
- Risk: low. If a future feature needs `/api/resource/details`, re-add the impl.

### Commit 4 — Delete `SqliteStore.update`

- File: `src/campcli/infrastructure/store.py` lines 229–258 (~30 lines).
- Verify zero callers:
  - `rg -n "store\.update|\.update\(" src/campcli/` — only one hit at
    `src/campcli/application/poller.py:69`, which is `ids.update(p.tg_allowed_ids)`
    (a `set.update`, unrelated).
  - `rg -n "ProfileRepo.*update|repo\.update" src/campcli/` — empty.
  - The `ProfileRepo` Protocol in `domain/ports.py` does declare `update`; remove that
    too if no consumer references it.
- Action: remove `SqliteStore.update` method and the `update` entry from the
  `ProfileRepo` Protocol. If a future "edit profile" command is added, re-introduce.
- Verification: `uv run pytest tests/test_profile_repo.py tests/test_profile_cli.py
  tests/test_store.py` — green. The store layer is exercised by `create`/`list`/`delete`
  paths only.
- Risk: low. Documented in commit message: "no production edit-profile flow; can
  be reintroduced when one ships."

### Commit 5 — Delete `Poller.tick()` and `Poller._handle_commands()`

- File: `src/campcli/application/poller.py` lines 92–94 (`tick` definition) and
  lines 322–325 (`_handle_commands` definition).
- Current state: `tick` calls `_handle_commands`; `_handle_commands` is also called from
  inside `handle_commands_forever`'s loop body. Tests at `tests/test_poller.py:29, 39,
  47, 53, 63, 73, 85, 98` call `poller.tick()` directly.
- Verify production uses only `handle_commands_forever`:
  - `rg -n "poller\.tick|Poller\.tick" src/` — empty (no production call).
  - `src/campcli/composition/daemon.py:62` calls `poller.handle_commands_forever`.
- Action: refactor `tests/test_poller.py` to call the underlying primitives directly
  (the dedup step, the `_handle_commands` step) rather than going through `tick`. The
  simplest path: extract `_handle_commands` into a free function `handle_one_command_batch`
  in the same module, and have `handle_commands_forever` call it in a loop. Tests then
  call `handle_one_command_batch(poller)` instead of `poller.tick()`.
  - Concretely: rename `_handle_commands` → `handle_one_command_batch` (public), drop
    `tick` entirely. Update `tests/test_poller.py` to call
    `handle_one_command_batch(poller)` in place of `poller.tick()`.
- Verification: `uv run pytest tests/test_poller.py tests/test_daemon.py` — green.
  The dedup behavior under `handle_one_command_batch` is unchanged.
- Risk: medium. This is the only refactor that touches test files. Bounded by
  8 call sites, all in `tests/test_poller.py`.

### Commit 6 — Centralise `_run_profile_migration()` in the Typer callback

- File: `src/campcli/composition/cli.py` lines 283, 331, 456, 524, 547, 582, 607, 619,
  631, 647, 660, 675, 694, 792, 825, 858 (18 call sites).
- Refactor: Typer supports `@app.callback()` which runs before any subcommand. Move
  the single `_run_profile_migration()` invocation into the callback body. Remove the
  18 per-command invocations.
- Action:
  1. Confirm a `@app.callback()` exists in `cli.py` (or add one).
  2. Move `from .profile import _run_profile_migration` (if any) into the callback.
  3. Delete all 18 `_run_profile_migration()` calls from individual commands.
  4. Tests `tests/test_profile_cli.py` and `tests/test_migrate_profile.py` should
     still pass; they invoke CLI via Typer's `CliRunner`, which executes the callback
     first.
- Verification: `uv run pytest tests/test_profile_cli.py tests/test_migrate_profile.py
  tests/test_not_interested_repo.py` — green.
- Risk: low. The migration is idempotent and already designed to run once per CLI
  invocation (it checks a stamp on the profile DB). Centralising it preserves the
  invariant.

## Decision Document

- **Module deletions:** `application/profile.py` (stub), `requirements.txt` (legacy
  dep file).
- **Method deletions:** `BCParksApi.resource_details` impl (Protocol kept),
  `SqliteStore.update` (Protocol entry kept or removed — TBD per commit 4),
  `Poller.tick` (renamed `_handle_commands` → `handle_one_command_batch` to keep
  dedup logic).
- **Module reorganisation:** `_run_profile_migration()` invocation moved from 18
  per-command call sites into the Typer `@app.callback()`. The function itself
  stays where it is.
- **Test changes:** `tests/test_poller.py` updates 8 `poller.tick()` calls to
  `handle_one_command_batch(poller)`. All other test files unchanged.
- **Architectural invariants preserved:**
  - `BCParksApi` Protocol in `domain/ports.py` unchanged.
  - `ProfileRepo` Protocol in `domain/ports.py` updated to remove `update` if no
    caller exists.
  - `application/poller.py` public API (`handle_commands_forever`,
    `handle_one_command_batch`, `run_search_once`) unchanged in spirit.
  - `pyproject.toml` is the single source of truth for runtime deps.
- **No new dependencies added; no schema changes; no public CLI surface changes.**

## Testing Decisions

- A good test exercises external behavior (CLI invocation, Telegram call shapes,
  SQLite row contents, Telegram update handling) — not internal helper names.
- The refactor preserves existing test coverage:
  - `tests/test_telegram.py` covers `set_my_commands`, `send_to`, chunking.
  - `tests/test_poller.py` covers `handle_commands_forever` (now indirectly via
    `handle_one_command_batch`) and dedup behavior.
  - `tests/test_profile_repo.py`, `tests/test_profile_cli.py`,
    `tests/test_migrate_profile.py`, `tests/test_not_interested_repo.py` cover
    profile CRUD + migration.
  - `tests/test_availability.py` covers `check_map`, `check_park`.
- No new tests required for the deletions: removing dead code is verified by the
  existing test suite continuing to pass.
- Prior art for the test style: `tests/conftest.py` provides `FakeBCParksApi`,
  `FakeTelegram`, and `make_poller()` helpers. The `handle_one_command_batch`
  refactor in commit 5 uses these directly.
- One test file will be modified: `tests/test_poller.py` (8 mechanical call-site
  rewrites).

## Further Notes

- **Why not also delete the Yagni items?** They were tempting (Telegram menu,
  `command_router` dispatch, `pricing.py` seasonal estimate, poller dedup helpers),
  but each has at least one production caller or test exercising it. The cost of
  removing them is higher than the cost of leaving them. A future pass can revisit
  each with a specific replacement story (e.g., "delete `pricing.py` when the live
  endpoint lands").
- **Why is this plan conservative?** Three of the originally-identified items
  (`Poller.tick`, `HttpxTelegram._chunks`, `AvailableSite`) were flagged in the
  initial audit as dead but turned out to have passing tests. This plan only
  touches items whose deadness is unambiguous.
- **Estimated effort:** ~2 hours. Six small commits, one human review each. No
  coordination with feature work needed; can land any time.
- **Follow-up issues to file (not part of this plan):**
  - "Yagni: collapse Telegram bot menu registration for one entry"
  - "Yagni: flatten `command_router` two-level dispatch dicts"
  - "Yagni: replace `pricing.py` with `None` once live endpoint lands"
  - "Shrink: extract `Poller` dedup helpers"