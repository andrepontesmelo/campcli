# Progress Log

## Session: 2026-06-21 — Architecture review + plan

### Architecture review completed
- Analysed full codebase: `src/campcli/` (5 layers, ~30 modules)
- Identified 4 architectural improvement candidates
- Wrote HTML report to `/tmp/architecture-review-campcli-20260621.html`
- **Selected candidate:** Extract notification from Poller, delete dead SearchNotifier

### Next session: Phase 1 — Audit current shape
- Read ports.py, poller.py, filters.py, format.py, test_poller.py
- Map every line of notification flow
- Decide whether to keep existing SearchNotifier Protocol or revise

### Session: 2026-06-21 (continued) — Phase 1 audit
- Read all 5 target files
- Confirmed `SearchNotifier` Protocol is dead (no callers anywhere)
- Mapped `_dispatch_match`: dedup → filter → record-suppressed → format → send
- Found subtle behavior: blocked/filtered matches are still added to `_seen` so they don't re-fire next tick — test `TestPollerBlocked` asserts this
- Findings written to findings.md

## Session: 2026-06-21 — Phases 2-5 implementation

### Phase 2: Implement SearchNotifier adapter
- Created `application/search_notifier.py` with concrete `SearchNotifier` class
- Interface: `start_poll(bookings, blocked_ids)` / `notify(match)` — owns dedup (`_seen`), filter, format, Telegram send
- Wired into `Poller.__init__` as `notifier` parameter

### Phase 3: Delete dead Protocol + old code
- Removed `SearchNotifier` Protocol from `domain/ports.py` (zero callers)
- Removed `_dispatch_match` and `_seen` from `Poller`
- Removed dead imports (`Booking`, `filters`, `render_match_message`, `datetime.date`)

### Phase 4: Tests
- Created `tests/test_search_notifier.py` with 4 unit tests (dedup, blocked suppression, seen bookkeeping)
- Added `FakeSearchNotifier` to `tests/conftest.py`
- Updated `test_poller.py`: removed dedup/blocked tests, added wiring test (`test_tick_calls_start_poll`)
- Full suite: 42 passed

### Phase 5: Type-check and lint
- mypy: 0 issues (30 source files)
- pytest: 42 passed

## Files changed
| File | Action |
|------|--------|
| `src/campcli/application/search_notifier.py` | Created |
| `src/campcli/domain/ports.py` | Deleted dead Protocol |
| `src/campcli/application/poller.py` | Added notifier seam, removed notification logic |
| `src/campcli/composition/daemon.py` | Wired SearchNotifier |
| `tests/conftest.py` | Added FakeSearchNotifier fixture |
| `tests/test_poller.py` | Rewired to use fake notifier |
| `tests/test_search_notifier.py` | Created |
