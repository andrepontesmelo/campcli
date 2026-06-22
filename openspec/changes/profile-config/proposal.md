## Why

The search profile is hardcoded in `constants.py` — patterns, horizon, drive-time limit, minimum start date, and booking-gap rule are all source constants. Changing them requires editing Python code. There is no allowlist mechanism to limit searches to specific Parks or Maps.

## What Changes

- Replace the hardcoded `dict` profile with a Pydantic `Profile` model persisted as `~/.campcli/profile.json`.
- Human-friendly pattern notation: `["fri-sun"]` instead of `[(4, 2)]`.
- Rename fields: `horizon_months` → `max_horizon_months`, add `min_start_date`, `rest_days_between_bookings`, `allowed`.
- Generate a default `profile.json` on startup if missing.
- Wire `min_start_date` into `expand_windows` (replacing `PERSONAL_MIN_START_DATE`).
- Wire `rest_days_between_bookings` into `NotificationPolicy` (replacing module-constant `REST_DAYS`).
- Wire `allowed` into `search.run()` as a park+map whitelist; resolve names via park catalog at load time.
- Error on unknown park/map names in `allowed` at startup (fail-fast).
- **BREAKING**: `PERSONAL_MIN_START_DATE` constant removed; `DEFAULT_PROFILE` constant removed; `build_profile()` removed.
- CLI `search` and daemon both read from the same `profile.json`.

## Capabilities

### New Capabilities

- `profile-config`: A JSON-backed search profile with human-friendly patterns, park/map allowlist, configurable start-date floor, and configurable booking-gap suppression. Replaces hardcoded constants with a single file.

### Modified Capabilities

(none — no existing specs to modify)

## Impact

- **Removed**: `DEFAULT_PROFILE` constant, `PERSONAL_MIN_START_DATE` constant, `build_profile()` function
- **Modified**: `search.py` (accept `Profile` instead of `dict`, wire `min_start_date` and `allowed`), `notification_policy.py` (accept `rest_days`), `poller.py` (load `Profile`, pass `rest_days` down), `daemon.py` (load profile file), `cli.py` (load profile for `search` command), `constants.py` (remove dead constants), `filters.py` (remove `REST_DAYS` constant or keep as default)
- **New**: `application/profile.py` (Pydantic model + loader)
- **Config**: `~/.campcli/profile.json` (generated on first run)
