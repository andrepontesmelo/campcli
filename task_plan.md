# Task Plan: Extract notification from Poller, delete dead SearchNotifier

## Goal
Deepen the Poller module by extracting real `SearchNotifier` adapter; delete unused `SearchNotifier` Protocol from `ports.py`. Notification logic (dedup, filtering, formatting, Telegram send) moves behind a single seam, testable without Poller setup.

## Current Phase
All phases complete

## Phases

### Phase 1: Audit the current shape
- [x] Read `domain/ports.py` — understand `SearchNotifier` Protocol and what calls it
- [x] Read `application/poller.py` — map `_dispatch_match`, `_seen`, notification flow
- [x] Read `application/filters.py` — `should_notify`, `gap_days_to_nearest`
- [x] Read `presentation/format.py` — `render_match_message`
- [x] Read `tests/test_poller.py` — existing coverage of notification
- **Status:** complete

### Phase 2: Implement SearchNotifier adapter
- [x] Decide interface: keep existing Protocol or revise — concrete class, no Protocol needed
- [x] Create `application/search_notifier.py` with `SearchNotifier` adapter
- [x] Move `_seen` dedup state into notifier
- [x] Move `_dispatch_match` notification logic into notifier
- [x] Wire `SearchNotifier` into `Poller.__init__` seam
- **Status:** complete

### Phase 3: Delete dead Protocol + old code
- [x] Remove unused `SearchNotifier` Protocol from `domain/ports.py`
- [x] Remove `_dispatch_match`, `_seen` from `Poller`
- [x] Verify no dead imports remain
- **Status:** complete

### Phase 4: Tests
- [x] Write unit tests for `SearchNotifier` in isolation
- [x] Update `test_poller.py` — Poller tests use fake notifier
- [x] Add `FakeSearchNotifier` conftest fixture
- [x] Run full test suite (42 passed)
- **Status:** complete

### Phase 5: Type-check and lint
- [x] Run mypy (0 issues)
- [x] Run pytest (42 passed)
- **Status:** complete

## Key Questions
1. Should SearchNotifier receive `drive_times` for formatting, or accept pre-formatted text?

## Decisions Made
| Decision | Rationale |
|----------|-----------|
|           |            |

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
|       | 1       |            |
