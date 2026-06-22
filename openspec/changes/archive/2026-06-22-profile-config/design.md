## Context

Current state: search profile is a hardcoded `dict` in `constants.py` (`DEFAULT_PROFILE`). `PERSONAL_MIN_START_DATE` is a module-level constant clamping window expansion. `REST_DAYS` in `filters.py` is a module-level constant. No allowlist exists. Changing any of these requires editing Python source.

Goal: one JSON file at `~/.campcli/profile.json` controls all search behaviour. CLI `search` and the daemon both read it. No code edits needed to change preferences.

Layers per ADR-0010: new `application/profile.py` (Application layer) holds the Pydantic model and loader. Composition root (`cli.py`, `daemon.py`) loads the file and passes the `Profile` value object down.

## Goals / Non-Goals

**Goals:**
- Single source of truth for search preferences (`profile.json`)
- Human-editable JSON with friendly pattern notation
- Park/map allowlist with name-based resolution, fail-fast on unknown names
- Min start date floor, configurable booking-rest gap
- Backward-compatible: missing file → generate defaults; CLI flags override profile values

**Non-Goals:**
- CLI management commands (`campcli profile set ...`) — manual edit only for now
- Profile reload without daemon restart
- Per-profile multi-profile switching
- UI/web interface for profile editing

## Decisions

### D1: Pydantic model over plain dict
The current `dict` profile has no validation. A Pydantic `BaseModel` with `model_validate` on JSON load gives schema validation for free, matches the existing `domain/models.py` style (Booking, BlockedPark, etc. are all Pydantic).

### D2: Profile lives in `application/` not `domain/`
Profile is application configuration, not a core domain entity. It maps to user preferences, not business invariants. The `Park`, `Map`, `Booking` domain models don't depend on it. Application layer per ADR-0010.

### D3: Name-based `allowed` resolution at load time
User writes `"Cultus Lake"`, not `-2147483645`. Resolution hits the park catalog API at load time. If a name doesn't resolve, fail-fast with a clear error — don't silently skip parks. This means profile loading needs a `BCParksApi` or a catalog list. The daemon has the API available. CLI `search` also uses `list_parks()`. Both can pass the park list into the profile loader.

Alternative rejected: store numeric IDs in JSON. Requires user to look up IDs. Worse UX.

### D4: Generate `profile.json` if missing, don't fail
Match the behaviour of `catalog.json` and `drive_times.json` — created on first use. A missing `profile.json` is the common first-run case. Generating defaults is friendlier than crashing.

### D5: `allowed` as resolved IDs after load
Profile loader resolves park/map names to numeric IDs after validation. `Profile` model holds resolved `allowed_park_ids: dict[int, set[int] | None]` where `None` means "all maps". The Pydantic model for JSON has `allowed: list[AllowedEntry]` with string names. After load, a separate `ResolvedProfile` or resolved field carries the IDs. This keeps name resolution at the boundary.

### D6: `rest_days_between_bookings` flows through `NotificationPolicy.__init__`
Currently `is_too_close()` accepts `rest_days` as a parameter defaulting to `REST_DAYS`. Change: `NotificationPolicy.__init__` accepts `rest_days: int = 14`, stores it, passes it to `is_too_close()` in `decide()`. Keep `filters.is_too_close` signature unchanged for backward compat (it still accepts the kwarg).

### D7: `fri-sun` → 3 nights
User's intent: `fri-sun` means arrive Friday, leave Monday = 3 nights (Fri, Sat, Sun). This is different from the current default `(FRIDAY, 2)` which was Fri-Sat (2 nights). Update the default pattern.

## Risks / Trade-offs

- **[Risk] Profile file hand-edited with bad JSON** → Pydantic `model_validate_json` catches it, exits with clear error.
- **[Risk] Catalog stale when resolving allowed names** → Load catalog fresh at profile-load time (both CLI and daemon already call `api.list_parks()`). If API unreachable, exit with error.
- **[Risk] Pattern format `fri-sun` ambiguous (wrap-around?)** → Only allow start→end within same Mon-Sun week. Document clearly.
- **[Trade-off] No CLI editor** → User edits JSON manually. Trade-off: simplicity vs safety. Acceptable for now; CLI commands can be added later.

## Migration Plan

1. Add `application/profile.py` with Pydantic model and loader
2. Add profile load to `cli.py` before `search` command
3. Add profile load to `daemon.py` `run_forever()`
4. Wire `min_start_date` into `expand_windows()`
5. Wire `rest_days_between_bookings` into `NotificationPolicy` / `SearchNotifier`
6. Wire `allowed` into `search.run()` as resolved park/map ID whitelist
7. Remove `DEFAULT_PROFILE`, `PERSONAL_MIN_START_DATE`, `build_profile()` from `constants.py` and `search.py`
8. Update tests
9. Run full test suite + mypy

Rollback: re-add the removed constants (they're just constants). The JSON file on disk has no effect if code doesn't read it. No database migration needed — `profile.json` is a new file.

## Open Questions

(none — all resolved during interview)
