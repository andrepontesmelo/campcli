# PRD: Mark NotInterested

## Problem Statement

A campcli user running the daemon receives Telegram notifications for available campsites. Some of these suggestions are for Parks or date ranges the user is simply not interested in — but the system has no way to record that preference. The daemon keeps suggesting the same Park for the same date range cycle after cycle, creating noise in the notification feed and making it harder to spot genuinely useful openings.

The user wants to tell the system, once, "don't show me this Park for these dates again on this profile," and have the system respect that preference across all future poll cycles.

## Solution

Introduce **NotInterested** — a profile-scoped preference statement that says: "for this Profile, do not suggest this Park on this specific date range again." The user expresses NotInterested by replying `/not-interested` to a daemon notification message in Telegram, or by managing entries via CLI (`profile not-interested add/rm/list`).

The daemon's SearchNotifier loads each profile's NotInterested entries at poll start and silently skips any WeekendMatch whose `(park_id, start_date, end_date)` tuple matches an entry. Notifications for the same Park on different dates are unaffected.

Under the hood, sent notification messages are tracked in a lightweight `sent_notifications` table so the system can resolve which Park and dates a reply refers to.

## User Stories

1. As a campcli user receiving daemon Telegram notifications, I want to reply `/not-interested` to a notification message, so that this Park on these dates is never suggested for my profile again.
2. As a campcli user, I want the daemon to confirm my NotInterested was recorded, so that I know the system heard me.
3. As a campcli user, I want previously-marked NotInterested entries to be silently skipped in all future poll cycles, so that my notification feed only shows Parks and dates I still care about.
4. As a campcli user, I want to list all NotInterested entries for my profile, so that I can review what I have muted.
5. As a campcli user, I want to remove a NotInterested entry (e.g., my plans changed), so that the Park on those dates is suggested again.
6. As a campcli user managing profiles via CLI, I want to add a NotInterested entry manually with the park name and date range, so that I can mute suggestions without waiting for a notification.
7. As a campcli user, I want to delete my profile and have all associated NotInterested entries cascade-deleted, so that no orphaned data remains.
8. As a campcli user with multiple profiles, I want NotInterested to be scoped per-profile, so that marking a Park as not-interested on one profile does not affect another profile's suggestions.
9. As a daemon operator, I want the NotInterested filtering to be efficient (O(1) lookup per WeekendMatch), so that it does not add latency to the poll cycle.
10. As a developer, I want sent notification tracking to be self-cleaning (old rows eventually purged), so that the tracking table does not grow unbounded.

## Implementation Decisions

### Domain model

**NotInterested** is a value object, not an aggregate root. It represents a profile-level preference expressed as a `(profile_id, park_id, date_start, date_end)` tuple. It does not carry an identity — it is uniquely identified by its composite key.

A `NotInterestedRepo` protocol is defined in `domain/ports.py` alongside existing protocols. The concrete implementation lives in `infrastructure/store.py`.

### DB schema

```sql
CREATE TABLE IF NOT EXISTS profile_not_interested (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    park_id INTEGER NOT NULL,
    date_start TEXT NOT NULL,
    date_end TEXT NOT NULL,
    UNIQUE(profile_id, park_id, date_start, date_end)
);

CREATE TABLE IF NOT EXISTS sent_notifications (
    message_id INTEGER PRIMARY KEY,
    profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    park_id INTEGER NOT NULL,
    date_start TEXT NOT NULL,
    date_end TEXT NOT NULL
);
```

`sent_notifications` rows are purged after a TTL (e.g., 90 days) during daemon startup. The table is purely operational — it maps Telegram message IDs to the Park and dates they represent, so reply commands can resolve context.

### NotInterestedRepo protocol

```python
class NotInterestedRepo(Protocol):
    def add(self, profile_id: int, park_id: int, date_start: date, date_end: date) -> None: ...
    def remove(self, profile_id: int, park_id: int, date_start: date, date_end: date) -> None: ...
    def list_for(self, profile_id: int) -> list[NotInterested]: ...
    def load_skip_set(self, profile_id: int) -> set[tuple[int, date, date]]: ...
    def record_sent(self, message_id: int, profile_id: int, park_id: int, date_start: date, date_end: date) -> None: ...
    def lookup_sent(self, message_id: int) -> tuple[int, int, date, date] | None: ...
```

`load_skip_set` returns a set of `(park_id, date_start, date_end)` tuples for O(1) lookup during the notify loop.

### Telegram handler

The `/not-interested` handler is a conditional text command — it only fires when `TelegramUpdate.reply_to_message_id` is populated (the user replied to a notification). If used standalone, it replies: "Reply this command to a notification message."

Handler flow:
1. Extract `reply_to_message_id` from the update
2. Look up `sent_notifications` via `NotInterestedRepo.lookup_sent()` — returns `(profile_id, park_id, date_start, date_end)` or None
3. If None → reply "Could not find the notification for this message (may have been purged)."
4. Verify `from_id` is in the profile's `tg_allowed_ids`
5. Insert into `profile_not_interested`
6. Reply confirming the entry was recorded

`/not-interested` is NOT registered as a bot command — it is only meaningful as a reply and would clutter the command menu.

### TelegramUpdate changes

`TelegramUpdate` gains an optional `reply_to_message_id: int | None = None` field. The `poll_updates()` parser in `infrastructure/telegram.py` extracts it from `message.reply_to_message.message_id`.

### send_to() return type change

`Telegram.send_to()` changes from `-> None` to `-> int`, returning the Telegram message_id from the API response. This affects all callers, but the ID is needed by `SearchNotifier` to record sent notifications.

### SearchNotifier changes

`SearchNotifier` receives `NotInterestedRepo` via its constructor. At `start_poll()`, it calls `load_skip_set(profile_id)` and stores it for the poll cycle. During `notify()`, before delegating to `NotificationPolicy`, it checks the skip set — if `(match.park_id, match.start_date, match.end_date)` is present, the match is silently dropped.

After a successful `send_to()` call, `SearchNotifier` records the sent message via `NotInterestedRepo.record_sent()`.

### CLI commands

Commands live under the existing `profile` group:

```
campcli profile not-interested add <profile_name> <park_name> <date_start> <date_end>
campcli profile not-interested rm <profile_name> <park_name> <date_start> <date_end>
campcli profile not-interested list <profile_name>
```

Park names are resolved via the BC Parks catalog API (same `resolve_park()` used by the Poller).

### Notification message footer

Notification messages include a footer: `Reply /not-interested to stop seeing this park for these dates.` This is added by `render_match_message()`.

## Testing Decisions

Tests verify external behavior through protocol seams — never through implementation details.

**What makes a good test:**
- Exercise the protocol boundary (repo, notifier, CLI, Telegram handler)
- Use in-memory SQLite for repo tests (no disk)
- Use mock `Telegram` protocol for SearchNotifier tests
- CLI tests run `subprocess` like existing profile CLI tests

**Modules tested:**

| Module | Test type | Seam |
|--------|-----------|------|
| `NotInterestedRepo` (SqliteStore) | Unit — in-memory SQLite | `domain/ports.py` protocol |
| `SearchNotifier` filtering | Unit — mock repo | NotInterestedRepo injected |
| `command_router` /not-interested handler | Unit — mock update + repo | `dispatch()` function |
| `poll_updates()` reply_to_message_id | Unit — JSON fixture | parser function |
| `Telegram.send_to()` return value | Unit — mock assert | Mock `Telegram` |
| CLI `profile not-interested` | Integration — subprocess | `test_cli_profile.py` pattern |
| Cascade delete (profile → not_interested) | Unit — in-memory SQLite | `ON DELETE CASCADE` |

**Prior art:**
- `tests/test_profile_repo.py` — in-memory SQLite repo tests
- `tests/test_cli_profile.py` — CLI subprocess integration tests
- `tests/conftest.py` — `FakeSearchNotifier`, `FakeStore`, mock `Telegram`

## Out of Scope

- **Thumbs-down reaction**: captured as `[S] thumbs-down-reaction-not-interested` — adds `message_reaction` handling to `poll_updates()` as a parallel input channel.
- **Pre-crawl API optimization**: running pattern explosion before the API call to skip parks with zero candidate windows. Deferred — the current architecture makes one API call per (park, map) pair for the full horizon, and pattern explosion is in-memory; the optimization is not worth the Poller refactor.
- **NotInterested expiry**: entries persist until manually removed. No auto-expiry or date-matching logic.
- **Edit existing NotInterested**: add and remove cover all cases; no edit command.

## Further Notes

- `sent_notifications` uses `message_id` as PRIMARY KEY — Telegram message IDs are unique per bot.
- Old `sent_notifications` rows are purged on daemon startup (rows older than 90 days) to prevent unbounded growth.
- The `UNIQUE` constraint on `profile_not_interested(profile_id, park_id, date_start, date_end)` prevents duplicate entries.
- `NotInterested` is a value object, not an aggregate root — it doesn't carry identity beyond its composite key.
- The `id` column on `profile_not_interested` exists for SQLite conventions but is not exposed in the domain model.
