---
type: gotcha
title: Daily availability grid is positional and date-less
description: BC Parks /api/availability/map daily slots are an ordered per-night array with no date field — slice by index offset from the fetch start, never by a slot date.
tags: [api, availability, bcparks, daemon]
timestamp: 2026-06-28
---

# Daily availability grid is positional and date-less

`GET /api/availability/map` returns `resourceAvailabilities` as
`{site_id: [slot]}`. The slot shape depends on `getDailyAvailability`:

- **`getDailyAvailability=false`** (default): **one aggregate slot** per site
  for the whole `[startDate, endDate)` range. A multi-night window that spans a
  reserved night returns a single non-zero code (e.g. `7`).
- **`getDailyAvailability=true`**: **one slot per night**, an ordered array
  `[{availability, remainingQuota}, …]`. Slot index `i` is the night
  `startDate + i days`.

**The trap:** in *both* modes the slot dicts have **no `date` field**. The grid
is purely positional. Availability codes live in
[`goingtocamp_codes.py`](../src/campcli/domain/goingtocamp_codes.py):
`0 = AVAILABLE`, `1 = RESERVED`, `2 = CLOSED`, `3 = WALK_IN`.

## Why it matters

The daemon poll path bulk-fetches one daily grid per (park, map) over the whole
horizon (`start = today`), then slices each weekend window locally in
`check_map_from_data` ([`availability.py`](../src/campcli/application/availability.py)).
The window `[start, start + nights)` maps to slot indices
`[offset, offset + nights)` where `offset = (start - fetch_start).days`. A site
is bookable for the window iff every one of those nights is present and code `0`.

This was [silently broken in prod](#history): the old code filtered slots by a
`s.get("date")` that never exists, so `window_slots` was always `[]` and the
daemon **never reported any opening**. The unit tests passed only because the
fakes fabricated date-keyed slots the real API never returns.

Verified against PROD (Liard River Hot Springs): "all nights in window code 0"
matches the authoritative `getDailyAvailability=false` aggregate answer for the
2-night weekend windows campcli cares about.

## History

Fixed 2026-06-28: `map_availability` gained a `daily: bool` flag;
`check_map_from_data` now takes `fetch_start` and slices positionally. The live
interactive path (`check_map`) still uses the `false` aggregate mode and is
unaffected.
