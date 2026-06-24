# PRD: Multi-Profile

## Problem Statement

campcli currently supports only one search profile — a singleton JSON file at `~/.campcli/profile.json`. This makes it impossible to monitor different campgrounds with different search criteria and notify different Telegram users independently. A user who wants to watch "Golden Ears" on weekends and "Garibaldi" on weekdays, each with its own Telegram recipient list, has no way to express this.

The system must support multiple independently-configured profiles, with the daemon crawl optimized so that overlapping park watches do not trigger redundant API calls.

## Solution

Replace the single `profile.json` with a multi-profile system stored in the SQLite database. Each profile holds its own search parameters (patterns, parks, drive-time, horizon, telegram targets) and can be independently enabled/disabled. The daemon crawl groups profiles by the parks they watch, calls the BC Parks API once per unique park, and fans results out to all interested profiles immediately — before moving to the next park.

A CLI subcommand (`campcli profile`) provides full CRUD management. The existing `profile.json` is migrated into the DB on first run and then deleted. The `watches`, `bookings`, and `blocked_parks` tables and their associated CLI commands are removed (ADR-0011).

## User Stories

1. As a campcli user, I want to create a new search profile with a name, so that I can maintain separate search configurations for different camping scenarios.
2. As a campcli user, I want to list all my profiles and see which are enabled or disabled, so that I can understand my current monitoring state at a glance.
3. As a campcli user, I want to add parks to a profile using park name queries, so that each profile watches its own set of campgrounds.
4. As a campcli user, I want to add flexible date patterns (e.g. `fri-mon:2-3`) to a profile, so that each profile searches its own date windows.
5. As a campcli user, I want to specify per-profile drive-time limits and search horizon, so that nearby parks and far-away parks are monitored separately.
6. As a campcli user, I want to add Telegram user IDs to a profile, so that availability notifications go to the right people.
7. As a campcli user, I want to enable or disable a profile without deleting it, so that I can pause monitoring for a configuration I intend to use later.
8. As a campcli user, I want to delete a profile and all its associated data (parks, patterns, telegram IDs), so that I can clean up unused configurations.
9. As a campcli user, I want to run a one-off search for a single profile, so that I can manually check availability for a specific configuration.
10. As a campcli user running the daemon, I want all enabled profiles to be monitored automatically, so that I don't need to select profiles at daemon startup.
11. As a campcli user, I want profile commands to not require `--profile` when exactly one profile is enabled, so that the single-profile case remains ergonomic.
12. As a daemon operator, I want park API calls to be deduplicated when multiple profiles watch the same park, so that the BC Parks API is not hammered with redundant requests.
13. As a daemon operator, I want notifications to fire immediately when a park's availability is known, before the next park is crawled, so that campsites are not lost to racing users.
14. As an existing campcli user, I want my current `profile.json` to be migrated into a DB profile on first run, so that my existing configuration is not lost.
15. As a developer, I want the profiles table to use fully normalized schema, so that queries like "find all profiles watching park X" are simple and efficient.

## Implementation Decisions

### Architecture

- Profiles move from a single Pydantic model loaded from JSON to a domain entity persisted in SQLite.
- The application layer exposes use-case functions (`create_profile`, `list_profiles`, `enable_profile`, etc.) that depend on a new `ProfileRepo` protocol.
- The Poller is refactored to accept multiple profiles: it groups enabled profiles by unique park, crawls sequentially per park, and fans out availability to each interested profile before crawling the next park.
- The `ProfileRepo` protocol is defined in `domain/ports.py` alongside existing protocols. The concrete implementation lives in `infrastructure/store.py`.

### Domain model

A `Profile` domain entity (Pydantic model in `domain/models.py`) replaces the application-layer `Profile` that currently lives in `application/profile.py`:

- `id: int | None`
- `name: str` (unique)
- `max_horizon_months: int` (default 3)
- `max_drive_hours: float` (default 3.0)
- `min_start_date: str | None`
- `rest_days_between_bookings: int` (default 14)
- `enabled: bool` (default True)
- `created_at: datetime | None`
- `updated_at: datetime | None`
- `patterns: list[PatternSpec]` — resolved from `profile_patterns` table
- `parks: list[ParkQuery]` — resolved from `profile_parks` table
- `tg_allowed_ids: list[int]` — resolved from `profile_telegram_ids` table

`PatternSpec` remains as-is in `application/profile.py`. A new `ParkQuery` value object holds the unresolved park search string and optional map string — resolved against the BC Parks catalog at poll/search time.

### DB schema

```sql
CREATE TABLE profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    max_horizon_months INTEGER NOT NULL DEFAULT 3,
    max_drive_hours REAL NOT NULL DEFAULT 3.0,
    min_start_date TEXT,
    rest_days_between_bookings INTEGER NOT NULL DEFAULT 14,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE profile_patterns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    pattern TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE profile_parks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    park_query TEXT NOT NULL,
    map_query TEXT
);

CREATE TABLE profile_telegram_ids (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    tg_id INTEGER NOT NULL
);
```

The `watches`, `bookings`, and `blocked_parks` tables are dropped. The `settings` table is retained.

### Poller refactor

The Poller's `run_search_once()` currently uses a single profile. After refactoring:

1. Load all enabled profiles from `ProfileRepo.list_enabled()`.
2. Collect unique `(park_id, map_id)` pairs across all profiles (resolving park/map queries against the BC Parks catalog at the start of each poll cycle).
3. For each unique pair, sequentially:
   a. Call `BCParksApi.map_availability()` **once**.
   b. For each profile watching this park, run the existing search/match logic (pattern explosion, availability check, prefer-longest dedup) and, if matches exist, notify via Telegram **immediately**.
   c. Proceed to the next park.
4. Telegram notification is per-profile: each profile's `tg_allowed_ids` receives only its own matches.

### CLI

New sub-command group: `campcli profile`

```
campcli profile create <name>       # interactive: prompts for parks, patterns, telegram IDs
campcli profile list                # table of profiles (name, enabled, park count, pattern count)
campcli profile show <name>         # full config dump
campcli profile edit <name>         # add/remove parks, patterns, telegram IDs
campcli profile delete <name>       # cascade delete
campcli profile enable <name>       # set enabled=1
campcli profile disable <name>      # set enabled=0
campcli profile search <name>       # one-off search for this profile
```

Existing commands (`search`, `check`, etc.) gain a `--profile` option. If omitted and exactly one profile is enabled, that profile is used automatically.

The old `telegram allow/revoke/list` commands move into `profile` as `campcli profile tg-add <name> <id>` / `tg-rm` / `tg-list`.

### profile.json migration

On first run of any profile command or daemon start, if `profile.json` exists and no profiles exist in the DB, the loader reads `profile.json`, creates a profile named `"default"`, populates all fields, and deletes `profile.json`. This is an ingest task within the feature — no separate migration CLI.

### Removals

Per ADR-0011:
- Drop `Watch`, `Booking`, `BlockedPark` domain models.
- Drop `WatchRepo`, `BookingRepo`, `BlockedParkRepo` protocols.
- Remove `watches.py`, `bookings.py`, `blocked.py` application services.
- Remove `watch`, `bookings`, `blocked` CLI sub-command groups.
- Remove corresponding methods from `SqliteStore`.
- Drop the `watches`, `bookings`, `blocked_parks` tables.

## Testing Decisions

Tests verify external behavior only — state in, state out, through public interfaces. No direct table inspection except in repository integration tests.

### What makes a good test

- Uses fake implementations of `BCParksApi`, `Telegram`, `Clock`, and `ProfileRepo` (duck-typed per ADR-0004, statically asserted with `Protocol`).
- Asserts on observable outcomes: which notifications were sent, which API calls were made, whether dedup occurred.
- Repository tests use a real in-memory SQLite database.

### Modules tested

| Module | Test type | Seams used |
|--------|-----------|------------|
| `domain/models.py` | Unit | Pure data — no seams needed |
| `application/profile_service.py` | Unit | Fake `ProfileRepo` + `Clock` |
| `application/poller.py` (multi-profile) | Unit | Fake `ProfileRepo`, `BCParksApi`, `Telegram`, `Clock` |
| `infrastructure/store.py` (ProfileRepo) | Integration | Real SQLite (in-memory) |
| `composition/cli.py` (profile commands) | Integration | Real SQLite, fake `BCParksApi` |
| Migration (profile.json → DB) | Unit | Fake `ProfileRepo`, temp JSON file |

### Prior art

- `tests/test_profile.py` — tests profile loading from JSON against the BC Parks API. Updated to test the new ProfileRepo-based flow.
- ADR-0004: test fakes use duck typing with Protocol static assertions. No mocking frameworks.

### Key test scenarios

1. Two profiles watch same park → API called once, both profiles notified with their respective matches.
2. Two profiles watch different parks → API called twice, each profile receives only its park's results.
3. Disabled profile is skipped by poller; its park is not crawled unless another enabled profile watches it.
4. Profile with no matching patterns → no notification (API still called, no matches).
5. ProfileRepo CRUD: create, read, update, delete with full cascade.
6. CLI `profile list` shows correct enabled/disabled state.
7. CLI defaults to only profile when exactly one is enabled.

## Out of Scope

- Profile import/export (JSON, YAML).
- Profile sharing or multi-user access control.
- Profile-specific API rate limits or crawl schedules.
- Cross-profile conflict detection (two profiles booking the same site).
- Web UI for profile management.
- Migration of `watches`/`bookings`/`blocked_parks` data — these tables are dropped without data preservation.

## Further Notes

- The crawl-dedup design is sequential per-park to keep the implementation simple. Parallel crawl across multiple parks remains a future optimization if latency becomes a bottleneck.
- Park queries stored in `profile_parks.park_query` are unresolved strings (same as today's `allowed.park` in profile.json). Resolution against the BC Parks catalog happens at poll/search time to handle parks that are renamed or reorganized.
- The `settings` table and `SettingsRepo` are retained unchanged; they hold configuration like the request interval throttle.
