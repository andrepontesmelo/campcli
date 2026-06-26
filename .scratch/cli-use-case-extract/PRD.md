# PRD: Extract CLI Use-Case Logic Into Application Layer

## Problem Statement

`composition/cli.py` is 882 lines with 38 functions — only 4 are Typer-wired commands, the remaining ~33 are use-case logic that belongs in the Application layer per ADR-0002 (composition root limited to wiring) and ADR-0010 (source tree mirrors the layers). Adding any new CLI command forces the developer to either bloat this file further or fragment logic across composition/ when it should live in application/. The file is hard to navigate, hard to test in isolation, and violates the architectural contract that the composition root does not contain business logic.

## Solution

Extract all non-wiring functions from `composition/cli.py` into Application-layer modules, following ADR-0005 (grouped by Domain noun). The composition root shrinks to Typer command wrappers that parse CLI arguments, call application use-case functions, and format results.

## User Stories

1. As a developer, I want to find profile-related logic in a single application module, so that I can understand the full profile workflow without reading CLI decorators.
2. As a developer, I want to add a new CLI command by writing only a thin Typer wrapper, so that I don't accidentally put business logic in the composition root.
3. As a developer, I want to test profile creation independently of the CLI, so that I can write faster tests that don't go through Typer.
4. As a developer, I want to test search logic independently of the CLI, so that search tests don't depend on Typer invocation.
5. As a developer, I want to test not-interested management independently of the CLI, so that not-interested behavior has focused tests.
6. As a code reviewer, I want to see a small `composition/cli.py` file with only wiring, so that I can mechanically verify that no business logic leaks into composition.
7. As a new contributor, I want to navigate from a CLI command to its implementation in one step (application module), so that I can trace the full call path without guessing where logic lives.

## Implementation Decisions

### Module split

Three new/extended application modules:

1. **`application/profile.py`** — Profile use cases extracted from `cli.py`:
   - `resolve_profile(repo, name) -> Profile` — resolves a profile name to a Profile object
   - `create_profile(repo, name, ...) -> Profile` — creates a profile with patterns, horizon, etc.
   - `list_profiles(repo) -> list[Profile]`
   - `show_profile(repo, id) -> Profile`
   - `edit_profile(repo, id, ...) -> Profile`
   - `delete_profile(repo, id)`
   - `enable_profile(repo, id)`
   - `disable_profile(repo, id)`
   - `search_profile(repo, api, drive_times, ...) -> list[WeekendMatch]`
   - `add_tg_id(repo, profile_id, tg_id)`
   - `remove_tg_id(repo, profile_id, tg_id)`
   - `list_tg_ids(repo, profile_id) -> list[int]`
   Note: ADR-0005 says "trivial DB-only commands skip the use-case layer." Assess each function; some may stay in `cli.py` if they're trivial repo calls.

2. **`application/search.py`** (extend existing) — Merge search/check flow from `cli.py`:
   - `search_for_profile(api, profile, drive_times, ...) -> list[WeekendMatch]`
   - `check_map(api, park, map_query, date_range, ...) -> list[AvailableSite]`
   - `book_open(api, park_id, map_id, date, nights) -> str` (booking URL)
   - `book_quote(api, park_id, map_id, date, nights) -> FeeEstimate`

3. **`application/not_interested.py`** — NotInterested use cases (profile-scoped):
   - `mark_not_interested(repo, profile_id, park_id, date_start, date_end)`
   - `remove_not_interested(repo, profile_id, park_id, date_start, date_end)`
   - `list_not_interested(repo, profile_id) -> list[NotInterested]`

### What stays in composition

- `_store()` — concrete adapter construction (SqliteStore)
- `api_call()` — concrete adapter construction (BCParksClient)
- `_run_profile_migration()` — migration orchestration (may move to `application/migrate_profile.py`)
- `_main_callback()` — Typer callback (reads config, sets up store + api, calls migration)
- `_confirm_profile_exists()` — CLI helper (exits with rich output, CLI concern)
- `_parse_hours()`, `_parse_hours_or_exit()`, `_parse_date_or_exit()` — CLI arg parsing
- The 4 Typer-wired commands: `check`, `search_cmd`, `doctor`, `daemon_cmd`
- All `@app.command()` and `@app.callback()` decorators

### Dependency injection pattern

Extracted use-case functions accept the same Protocol-typed ports already in use: `ProfileRepo`, `BCParksApi`, `SettingsRepo`, `NotInterestedRepo`, `DriveTimes`. No new ports. Follows ADR-0001.

### Non-goal

- No behavior changes to any command.
- No CLI output format changes.
- No database schema changes.

## Testing Decisions

### What makes a good test

Tests call the extracted use-case functions directly with duck-typed fake implementations of the ports (matching existing pattern in `tests/test_search.py`, `tests/test_profile.py`). Tests target external behavior (return values, side effects on repos), not implementation details.

### Prior art

- `tests/test_search.py` — tests `expand_windows`, search logic with `_AvailabilityApi` fake
- `tests/test_profile.py` / `tests/test_profile_repo.py` — profile CRUD tests
- `tests/test_not_interested_repo.py` — not-interested repo tests

### Modules tested

- `application/profile.py` — new test file or extend `tests/test_profile.py`
- `application/search.py` — extend `tests/test_search.py`
- `application/not_interested.py` — new test file or extend `tests/test_not_interested_repo.py`
- `composition/cli.py` — existing CLI integration tests continue to pass (test_profile_cli.py)

## Out of Scope

- Extracting daemon.py use-case logic (separate task)
- Splitting poller.py (separate task: poller-split)
- Refactoring `application/search.py` internals beyond what's needed for the merge
- Changing any CLI flag names or behavior

## Further Notes

- Order of operations: extract → verify existing tests pass → add new application-layer tests → remove dead code from cli.py.
- `_run_profile_migration` is infrastructure-level wiring. Evaluate moving to `application/migrate_profile.py` (which already has migration logic) or keeping in composition as thin wiring.
- `resolve_profile` and `_confirm_profile_exists` are closely related — `_confirm_profile_exists` calls `resolve_profile` and prints an error + exits if not found. The exit behavior is CLI-specific, so `_confirm_profile_exists` stays in composition and calls the extracted `resolve_profile`.
