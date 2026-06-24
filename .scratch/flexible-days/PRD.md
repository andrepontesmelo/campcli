# PRD: Flexible-Days Search

## Problem Statement

Today I can only tell campcli to search for a stay that begins and ends on
fixed weekdays — e.g. `fri-sun` means "arrive Friday, leave Sunday, exactly two
nights." If I would also accept a Saturday arrival, or a three-night stay over
the same long weekend, I have to add several separate patterns and reason about
each one by hand. There is no way to say "any 2-to-3-night stay somewhere
inside this Friday-to-Monday window," which is how I actually think about a
camping trip.

## Solution

Let a pattern describe a **span** of days plus a **minimum and maximum number of
nights**, and have the search enumerate every stay that fits inside the span
whose length falls in that range.

A pattern gains an optional suffix: `fri-mon:2-3` means "inside the Friday →
Monday span, find any stay of 2 or 3 nights." That expands to:

- `fri-sun` (2 nights)
- `sat-mon` (2 nights)
- `fri-mon` (3 nights)

A bare pattern keeps working exactly as before: `fri-sun` still means a single
two-night Friday→Sunday stay. So the old behaviour is just the special case
where min = max = the span's own length, and existing `profile.json` files need
no changes.

## User Stories

1. As a camper, I want to write `fri-mon:2-3`, so that the search finds every 2-
   or 3-night stay inside the Friday-to-Monday window in one pattern.
2. As a camper, I want a bare pattern like `fri-sun` to keep meaning a fixed
   two-night stay, so that my existing profile keeps working unchanged.
3. As a camper, I want to set min = max (e.g. `fri-sun:2-2`), so that I can pin a
   span to exactly one stay length when I want the old strictness explicitly.
4. As a camper, I want min < max to widen the stay lengths, so that I can catch
   both a short weekend and a longer one with a single line.
5. As a camper, I want the span to be able to differ from the nights, so that
   `fri-mon:2-3` can start on Friday OR Saturday, not only on the span's first
   day.
6. As a camper, I want each enumerated sub-window checked against availability
   independently, so that a site free only for the Saturday-arrival stay still
   surfaces.
7. As a camper, when the same arrival date has both a shorter and a longer
   available stay, I want to be told about the longest one only, so that I am
   not spammed with overlapping options for the same night.
8. As a camper, I want an obviously broken pattern (unknown day, end-before-
   start, min > max, min < 1) to fail loudly when the profile loads, so that I
   fix the typo before a search runs.
9. As a camper, I want a warning when a pattern expands into a large number of
   windows, so that I notice an accidentally huge span before it multiplies my
   API traffic.
10. As a camper, I want the booking URL, the notification, and the match's
    night count to all agree for each enumerated stay, so that what I click
    matches what I was told.
11. As a camper, I want the existing horizon, drive-time, allowlist, and
    rest-day filters to apply unchanged to every enumerated window, so that
    flexibility does not bypass my other constraints.
12. As a camper mixing styles, I want to list a bare pattern and a ranged
    pattern together (`["fri-sun", "fri-mon:2-3"]`), so that I can migrate one
    pattern at a time.
13. As a developer, I want the span-and-range model to live behind the existing
    `parse_pattern` / `expand_windows` seams, so that the change is unit-testable
    without new infrastructure.

## Implementation Decisions

### Pattern syntax — per-pattern suffix

A pattern string is `span` or `span:min-max`:

- `span` is the existing `startday-endday` form (e.g. `fri-mon`). The span's
  length in nights is `end_weekday - start_weekday` (no wrap-around, no
  same-day), as today.
- `:min-max` is an optional suffix giving the inclusive night-count range.
- A bare span is equivalent to `span:N-N` where `N` is the span's own nights.
  This is what preserves backward compatibility.

Validation, all at profile-load time (fail-fast, same place patterns are
already validated): unknown day name; end ≤ start; `min < 1`; `min > max`;
`max` greater than the span length (a stay can't be longer than its window).

### `parse_pattern` return shape

`parse_pattern` currently returns `(start_weekday, nights)`. It will return a
richer structure carrying `(start_weekday, span_nights, min_nights,
max_nights)` (exact container — named tuple / dataclass — is an implementation
choice for planning). The bare-pattern case sets `min = max = span_nights`.
`Profile.pattern_tuples()` (or a renamed successor) returns the list of these.

### Window enumeration in `expand_windows`

For each calendar date `d` in the horizon that equals a pattern's
`start_weekday`, enumerate every offset `o` in `0 .. (span_nights - min_nights)`
and every length `n` in `min_nights .. max_nights` such that the stay starting
at `d + o` of length `n` still ends on or before the span's end (`o + n <=
span_nights`). Emit `(start_date = d + o, nights = n)`. The existing past-date,
`min_start`, and `max_start` guards continue to apply to the **emitted start
date**.

Worked example, span Fri→Mon (`span_nights = 3`), min 2 max 3, anchored on a
Friday `d`:

- `o=0, n=2` → Fri→Sun (2n)
- `o=1, n=2` → Sat→Mon (2n)
- `o=0, n=3` → Fri→Mon (3n)
- `o=1, n=3` → rejected (`1 + 3 > 3`)

### Prefer-longest dedup (generalised)

The current search loop has a special case that suppresses a 1-night stay when
a 2-night stay covers the same or adjacent start. Generalise it: process each
map's candidate windows sorted by start date then by descending nights; track
which `(start_date)` nights are already covered by an accepted longer stay, and
skip a shorter window whose nights are wholly contained in an already-accepted
stay from the same or an earlier overlapping start. The intent — "tell me about
the longest available stay per arrival, not every sub-length" — is preserved;
only the hard-coded 1-vs-2 assumption is removed.

### Explosion guard — warn, do not cap

No hard limit on enumerated windows. When a single pattern expands beyond a
threshold (planning to pick a concrete number, order of ~10), emit a warning via
the existing progress/log side-channel so the user notices a runaway span. The
search still runs.

### Unchanged contracts

`WeekendMatch` keeps its `start_date` / `end_date` / `nights` fields; `end_date`
remains the checkout day per the recent convention fix (`end = start + nights`).
Horizon, drive-time filtering, allowlist pre-filtering, rest-day suppression,
and the booking-URL builder are untouched and operate per emitted window.

## Testing Decisions

Good tests here assert **external behaviour at the seam**, not internal loop
mechanics: given a profile and a clock, what set of `(start_date, nights)`
windows comes out, and which matches survive dedup. No test should reach into
the enumeration's offset arithmetic.

- **`parse_pattern`** (`tests/test_profile.py::TestParsePattern`, existing prior
  art): add cases for `fri-mon:2-3` parsing, bare-pattern `min=max=span_nights`
  equivalence, and each new validation error (`min<1`, `min>max`, `max>span`).
- **`expand_windows`** (`tests/test_search.py`, alongside
  `TestExpandWindowsMinStart`): assert the exact emitted window set for a ranged
  pattern over a known horizon and fixed `today`; assert a bare pattern emits the
  same windows as before the change (regression lock); assert `min_start` /
  `max_start` / past-date guards still filter emitted starts.
- **Prefer-longest dedup** (`tests/test_search.py::TestSearchRunWithAllowed`
  style, driving `run()` with the fake `_AvailabilityApi`): when a fake reports
  availability for both a 2- and 3-night stay from the same Friday, assert only
  the 3-night `WeekendMatch` is yielded; when only the shorter stay is available,
  assert it still surfaces.
- **Backward-compat integration**: a profile containing only `["fri-sun"]`
  yields the identical matches it does today (guards the migration promise).

Use the existing fakes (`FakeApi`, `_AvailabilityApi`, `_make_profile`) and the
injected clock; do not add new test infrastructure.

## Out of Scope

- Calendar-date spans (e.g. "any 2 nights between Jul 1 and Jul 10"). This PRD
  is weekday-anchored spans only.
- Wrap-around spans crossing the week boundary (e.g. `sat-mon` as a literal
  Sat→Mon **of the same weekend** is fine; `sun-sat` wrapping is still rejected).
- A hard cap / rejection on window explosion — warning only.
- Changing notification, booking-URL, or `WeekendMatch` schema.
- Per-pattern overrides of horizon, drive-time, or rest-day settings.

## Further Notes

The backward-compatibility story is the load-bearing design choice: because a
bare span collapses to `min=max=span_nights`, the entire feature is additive and
no existing `profile.json` changes. Recommend shipping with the explosion-
warning threshold conservative, then loosening once real usage is observed.

The recent night-count convention fix (`end_date` = checkout day, `nights = end
- start`, fri-sun = 2 nights) is assumed throughout; enumeration must not
reintroduce the old off-by-one.
