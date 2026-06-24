# ADR-0011: Deprecate watches, bookings, and blocked-parks tables

**Status:** Accepted
**Date:** 2026-06-24

## Context

The SQLite database currently has four tables: `watches`, `bookings`,
`blocked_parks`, and `settings`. The `watches` table supports a manual
one-off availability check (`campcli watch add` + `campcli watch run`)
that is separate from the daemon-driven search loop. `bookings` and
`blocked_parks` similarly have no active usage.

The multi-profile feature (ref. `[L] multi-profile`) requires a new
`profiles` table plus relationships. Keeping unused tables adds
maintenance cost to every schema migration and to the store adapter.

## Decision

**Deprecate and remove** `watches`, `bookings`, and `blocked_parks`
tables. Drop `WatchRepo`, `BookingRepo`, `BlockedParkRepo` protocols
and their infrastructure implementations. The `settings` table and
`SettingsRepo` are retained.

The `profiles` table (plus `profile_patterns`, `profile_parks`,
`profile_telegram_ids`) becomes the authoritative schema alongside
`settings`.

An ingest task will migrate the current single `profile.json` into a
DB profile named `"default"` and then delete the JSON file.

## Consequences

- **Positive:** Schema shrinks from 4 tables to 5 clearer ones
  (profiles + 3 children + settings). Store adapter code reduced.
  No entanglement between manual watches and profile-driven daemon.
- **Negative:** Removes existing CLI commands (`campcli watch`,
  `campcli booking`, `campcli blocked`) — these commands had no
  active usage per the maintainer.
