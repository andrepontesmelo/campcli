# Findings

## Architecture review candidates (2026-06-21)
Full HTML report at `/tmp/architecture-review-campcli-20260621.html`

### Candidate 1 (Strong — selected)
**Extract notification from Poller, delete dead SearchNotifier Protocol**

- `domain/ports.py:141–162` defines a `SearchNotifier` Protocol that is never implemented
- `application/poller.py` class owns notification, dedup, filtering, formatting, Telegram send
- Notification logic testable only through full Poller object setup
- Seam already exists as unused Protocol — just needs an adapter

### Other candidates
- Split `constants.py` by concern (holidays → `domain/holidays.py`, profile → `domain/profile.py`)
- Collapse `command_router.py` into Poller (shallow pass-through)
- Separate drive-time build from drive-time load in infrastructure/

## Architecture constraints from ADRs
- ADR-0001: Application depends on Protocols, never concrete adapters
- ADR-0002: Composition root limited to `cli.py` and `daemon.py`
- ADR-0005: Use-case functions grouped by domain noun, not classes
- ADR-0006: Repo + Clock ports in `ports.py`
- ADR-0010: Source tree mirrors Clean Architecture layers

## Phase 1 audit — current notification shape

### Protocol (ports.py:139–162)
`SearchNotifier` Protocol with two methods:
- `start_poll() -> None`
- `notify(match: WeekendMatch) -> None`

`WeekendMatch` is in `domain/models.py:28` (Pydantic model).

### Dead code confirmation
- `SearchNotifier` only appears at its own definition site (`ports.py:139, 141`)
- Zero callers in `src/campcli/` or `tests/`
- Confirmed: Protocol is dead

### Poller's notification responsibility (poller.py:91–116)
`_dispatch_match` does five things in order:
1. **Dedup**: skip if `(park_id, map_id, start_date, nights)` already in `self._seen`
2. **Filter**: call `filters.should_notify(m, bookings=..., blocked_park_ids=...)` — returns False if park blocked OR booking too close (<14 days)
3. **Record suppressed**: even when filter rejects, add key to `_seen` (so the same blocked match doesn't re-fire next tick)
4. **Format**: `render_match_message(m, prev_gap_days, next_gap_days, drive_times=self._drive_times)`
5. **Send**: `self._telegram.send(text)` with try/except logging, then add key to `_seen` on success

State `self._seen: set[tuple[int, int, date, int]]` lives on Poller (line 37).

### Test coverage (tests/test_poller.py)
- `TestPollerDedup` directly calls `poller._dispatch_match(m, [], set())` twice, asserts one send
- `TestPollerBlocked` calls `_dispatch_match(m, [], {1})` with blocked park, asserts zero sends AND asserts key in `poller._seen` (suppression-dedup behavior)

### Implications for Phase 2 interface
The Protocol's `start_poll()` / `notify()` split maps to Poller's per-tick flow:
- `tick()` calls `bookings = booking_repo.list_bookings()` and `blocked_ids = ...` once, then dispatches each match
- These two collections need to reach the notifier — either via `start_poll(bookings, blocked_ids)` (revise Protocol) or via ctor injection (Poller holds them, hands in)

### Interface question (already in plan)
Q1 from plan: should `SearchNotifier` receive `drive_times` for formatting, or accept pre-formatted text?
- Answer: receive `drive_times` — `render_match_message` already needs it (poller.py:108), and the Protocol's docstring says "format" is its job. Keeps Poller free of presentation logic.

### ADR alignment
- ADR-0001: notifier is a Protocol consumer — good
- ADR-0005: "use-case functions grouped by domain noun" — a `SearchNotifier` class is consistent if it has a single cohesive purpose (notify). Acceptable.
- ADR-0010: `application/search_notifier.py` is the right layer — it depends on Telegram (port) + filters (app) + format (presentation) + repos (port).
