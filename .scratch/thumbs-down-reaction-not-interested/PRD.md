# PRD: Thumbs-Down Reaction NotInterested

## Problem Statement

A campcli user receiving daemon Telegram notifications has one way to record **NotInterested**: type `/not-interested` in reply to the notification message. That's a friction point. Most reactions to a bad suggestion are non-verbal — the user *feels* "not this" and would prefer a one-tap gesture over typing a command. Today there is no such gesture, so suggestions the user has mentally rejected keep arriving cycle after cycle until the user decides to type a reply.

The same root preference (don't suggest this Park on these dates) lives in two unreachable channels: the reply-command path requires typing; the missing reaction path requires nothing. We need the latter.

## Solution

Add a Telegram **message reaction** input channel for **NotInterested**: when the user reacts with 👎 (thumbs-down emoji) on a daemon notification message, the bot records a NotInterested entry for the exact `(park_id, date_start, date_end)` of that notification, scoped to the profile that sent it. A brief confirmation reply is sent to the user. All future poll cycles skip matches against the new entry.

The reaction handler is authorization-gated and target-validated: only authorized Telegram users can trigger it, and only known notifications are accepted. Unknown or unauthorized reactions are silently ignored — they do not error, log spam, or reply.

The feature also fixes a latent schema bug discovered during design: `sent_notifications` currently keys on `message_id` alone, so reactions in chat A on `message_id 42` would collide with chat B's `message_id 42`. The primary key is extended to `(chat_id, message_id)` and threaded through all call sites. The same bug affects `/not-interested` reply commands and is fixed by the same change.

## User Stories

1. As a campcli user receiving daemon Telegram notifications, I want to react 👎 on a notification message, so that this Park on these exact dates is marked NotInterested for my profile without typing.
2. As a campcli user, I want a brief confirmation reply from the bot after reacting 👎, so that I know the suppression was recorded.
3. As a campcli user, I want reactions to target the exact `(date_start, date_end)` of the notification I reacted to, so that suppression is precise and does not affect other dates for the same Park.
4. As a campcli user, I want previously-recorded NotInterested entries (from any input channel — reaction, `/not-interested` reply, or CLI add) to be silently skipped in all future poll cycles, so that my notification feed only shows Parks and dates I still care about.
5. As a campcli user with multiple Telegram chats pointed at the same daemon, I want reactions to resolve the correct profile per chat, so that a reaction in chat A never silently suppresses a notification in chat B.
6. As a campcli user with multiple authorized users on one profile, I want any authorized user's 👎 reaction to record NotInterested, so that the team can collectively prune suggestions.
7. As a campcli user, I want a 👎 reaction on a notification that has already expired (older than the `sent_notifications` retention window) to receive a brief "could not find" reply, so that I understand the bot did not silently drop my gesture.
8. As a campcli user, I want a 👎 reaction from an unauthorized user to be silently ignored, so that the bot does not leak authorization state to a third party.
9. As a campcli user, I want to react 👎 on the same notification twice and have it remain a single NotInterested entry, so that the suppression list does not fill with duplicates.
10. As a campcli user, I want to react 👎 on a notification and later receive a different notification for the same Park on a different date, so that suppression is per-date, not per-Park.
11. As a campcli user, I want to undo a NotInterested entry via the existing CLI `profile not-interested rm` flow, so that the reaction channel does not become a one-way trap.
12. As a daemon operator, I want reaction handling to be a thin seam layered over the existing NotInterested repo, so that there is one suppression write path regardless of input channel.
13. As a daemon operator, I want `sent_notifications` to retain its existing 90-day TTL behavior, so that reactions targeting older notifications naturally fail fast (and reply with the not-found message).
14. As a developer, I want the reaction handler to add no new dependencies on Telegram-specific types beyond what already exists in the bot's update extractor, so that test fakes and mocks remain simple.
15. As a developer, I want the schema change to be additive (drop + recreate the affected table only, no backfill of historical rows), so that the migration is small and reversible.

## Implementation Decisions

### Reaction input shape

The handler accepts a Telegram `Update.message_reaction` payload. It extracts:

- `chat.id` (the Telegram chat that received the reaction)
- `message_id` (the message being reacted to)
- `from.id` (the Telegram user who reacted)
- `new_reaction[]` (the reactions just added)

A reaction update is accepted iff at least one entry in `new_reaction[]` has `type == "emoji"` and `emoji == "👎"`. Removing a reaction (an `old_reaction[]` entry with no compensating `new_reaction[]`) is ignored — suppression is one-way.

### Handler location

The reaction handler lives in `src/campcli/application/command_router.py` alongside the existing `dispatch()` entry point, as a new `_process_reaction(reaction_update, ...)`. It uses the same `ni_repo` (NotInterested repo) and `profile_repo` instances already wired in `dispatch()`. The Telegram `poll_updates` extractor in `src/campcli/infrastructure/telegram.py` grows a new branch alongside `message` and `callback_query` to surface `message_reaction` updates in the same iteration.

### Handler flow

1. Resolve the reaction's target notification via `ni_repo.lookup_sent(chat_id, message_id)`.
2. If miss: reply once with `"Could not find that notification — it may have expired."` and return. No state change.
3. If hit: take the `(profile_id, park_id, date_start, date_end)` tuple.
4. Check `from_id ∈ profile_repo.get_by_id(profile_id).tg_allowed_ids`. If not: silently return. No reply, no log spam, no state change.
5. Call `ni_repo.add(profile_id, park_id, date_start, date_end)`. The existing UNIQUE constraint on the `(profile_id, park_id, date_start, date_end)` tuple makes this idempotent — a duplicate 👎 is a no-op.
6. Reply with `"Ok, won't suggest {park.name} from {date_start:%b %-d} to {date_end:%b %-d}."` formatted in the user's local style.

### Schema change: chat_id scoping fix

`sent_notifications` PK is extended from `message_id` (single column) to `(chat_id, message_id)` (composite). `chat_id` becomes a NOT NULL column. The migration is a fresh-schema drop-and-recreate for that table only:

- All old rows in `sent_notifications` are discarded by the migration. Rationale: the only data they carry is `(profile_id, park_id, date_start, date_end)`, the table is already self-pruning via `purge_old_sent_notifications()` on a 90-day window, and the notifications those rows point to are also gone. No other table is affected.
- `record_sent` and `lookup_sent` signatures gain a `chat_id` parameter.
- All call sites are updated to pass `chat_id`: `SearchNotifier.notify` (which writes), the `/not-interested` reply handler (which reads), and the new `_process_reaction` handler (which reads).
- `profile_not_interested` (the destination of the suppression write) is unchanged. It is already keyed on `(profile_id, park_id, date_start, date_end)` and is not affected by the `sent_notifications` schema change.

### Confirmation reply text

The confirmation wording follows the existing `/not-interested` reply-command voice:

- Hit case: `"Ok, won't suggest {park.name} from {date_start:%b %-d} to {date_end:%b %-d}."` (e.g., `"Ok, won't suggest Maple Bay Campground from Sep 5 to Sep 7."`)
- Not-found case: `"Could not find that notification — it may have expired."`
- Not-authorized case: no reply.

### Domain model

No new domain entities. The reaction channel is a new input that writes to the existing **NotInterested** value object via the existing `NotInterestedRepo.add(...)`. The `SentNotification` record grows a `chat_id` field to support chat-scoped lookup; its identity becomes the composite `(chat_id, message_id)`.

### Ports and seams

- `NotInterestedRepo` (existing) — gains nothing new; the reaction path uses `add()` and `lookup_sent()` exactly as the reply command does.
- `SentNotificationRepo` (existing) — `record_sent` and `lookup_sent` signatures take `chat_id`.
- `ProfileRepo` (existing) — `get_by_id` is read to check `tg_allowed_ids` for the authorization gate.
- Telegram update extractor — extends to surface `message_reaction` updates.

### Race semantics

A 👎 reaction arriving during the same poll cycle where the user is about to receive a duplicate suggestion for the same Park/dates does not suppress the duplicate. The new NotInterested row takes effect on the *next* availability poll. This matches the existing `/not-interested` reply-command behavior — both input channels have the same race window. Closing the window would require a synchronous re-search on add, which is out of scope.

### Out-of-band behaviors

- Multiple 👎 in one update: handler iterates each; behavior is the same as a single 👎 (one reply per notification reaction update).
- Bot reacts to its own message: Telegram does not deliver bot self-reactions to the bot's `getUpdates`. Not a concern.
- Reactions on non-notification messages (e.g., admin chatter): `lookup_sent` returns nothing, and the handler replies with the same `"Could not find that notification — it may have expired."` text as the expired-notification case. The two cases are indistinguishable from the user's perspective and the reply is harmless. No silent suppression.

## Testing Decisions

### What makes a good test

Test external behavior at the highest reasonable seam. For the reaction handler, that is the unit boundary of `_process_reaction` with real SQLite + real `SqliteStore` + fake Telegram. The schema migration test asserts the new schema is in place after migration; it does not check internal cursor behavior.

### Seams

Three seams, listed in priority order:

1. **`_process_reaction` unit tests** — call the handler directly with synthetic reaction payloads and assert the side effects (NotInterested row added or not, Telegram replies sent or not). This is the de-risking test for the auth path, the miss path, and the hit path.
2. **End-to-end happy-path test** — inject a 👎 reaction into the bot's update stream, run the next `run_search_once` for that profile, assert the suppressed dates are not notified. Validates the full chain: reaction → repo → notifier filter.
3. **`poll_updates` extractor test** — feed mock `Update.message_reaction` payloads and assert the extractor surfaces `chat.id`, `message_id`, `from.id`, and `new_reaction[]` correctly. Same seam the existing `message` and `callback_query` extractor tests use.

A migration test creates a v1-schema DB (with `sent_notifications` keyed on `message_id` only), runs the migration, and asserts the new schema + that the table is empty post-migration (drop-and-recreate semantics).

### Modules covered

- `src/campcli/application/command_router.py` — `_process_reaction` and its dispatch integration.
- `src/campcli/infrastructure/telegram.py` — `poll_updates` extension.
- `src/campcli/infrastructure/store.py` — schema migration + `record_sent` / `lookup_sent` signature changes + `sent_notifications` schema.
- All call sites of `record_sent` and `lookup_sent` — must be updated and tested for `chat_id` plumbing.

### Prior art

The reaction handler is structurally identical to the existing `/not-interested` reply handler in `command_router.py:25-53` (lookup_sent → auth check → add → reply). New tests should mirror the shape of the existing reply-command tests in `tests/test_command_router.py` (or equivalent), extended with reaction-shaped inputs.

The migration test should mirror the shape of any existing schema-migration tests in `tests/test_migrate_profile.py` or `tests/test_store.py`.

## Out of Scope

- Any reaction emoji other than 👎. If we ever want 👍-means-archive or other gestures, this PRD explicitly does not anticipate them.
- Removing NotInterested entries via reactions (un-👎 does nothing; the only way to remove is the existing CLI `profile not-interested rm` flow).
- A synchronous re-search after a 👎 reaction to close the race window with the current poll cycle.
- Backfilling historical `sent_notifications` rows. The migration is drop-and-recreate.
- Telegram Premium star reactions, custom emoji reactions, or burst reactions. Only standard emoji reactions are handled.
- Bot-side emoji-reaction sending (the bot reacts with 🤖 or similar on the user's message after handling). The bot only sends text replies.
- Updating the NotInterested domain model. It remains a value object keyed on `(profile_id, park_id, date_start, date_end)`.

## Further Notes

- The `chat_id` schema fix is bundled with this feature because it is the same code path. Shipping them separately would either leave the bug latent for `/not-interested` replies (Q8 sub-issue) or require duplicated migration logic. The bundled change has independent value — anyone running the bot today has the latent bug.
- The 90-day `purge_old_sent_notifications()` behavior is preserved. Reactions on notifications older than 90 days naturally fall into the not-found reply path; no additional retention logic is added.
- The reaction handler is intentionally non-blocking with respect to the availability poll cycle. Race window is accepted per the prior-art reasoning above.
- The `tg_allowed_ids` authorization gate mirrors the gate in the existing `/not-interested` reply handler. No new authorization model is introduced.