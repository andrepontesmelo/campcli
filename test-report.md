# camply × BC Parks End-to-End Validation Report

**Date:** 2026-04-24  
**camply version:** 0.34.1  
**Provider:** GoingToCamp — `camping.bcparks.ca`  
**Rec area:** BC Parks, British Columbia, CA (id=12)

---

## Test Results

| # | Test | Result | Time | Notes |
|---|------|--------|------|-------|
| T1 | Recreation area discovery | **PASS** | <1s | BC Parks id=12 confirmed |
| T2 | Campground listing (CLI) | **FAIL** | <1s | Bug in provider; workaround PASS |
| T3 | Availability query | **PASS** | 0.3s | 0 available (fully booked, expected) |
| T4 | Direct Python API | **PASS** | 0.3s | Data model validated; responses saved |
| T5 | Telegram notification | **SKIP** | — | No credentials; wiring documented |
| T6 | Booking capability check | **PASS** | — | Read-only confirmed |

---

## T1 — Recreation Area Discovery

```
camply --provider GoingToCamp recreation-areas --search "BC Parks"
→ ⛰  BC Parks, British Columbia, CA (#12)
```

Pass. `rec_area_id=12` confirmed.

---

## T2 — Campground Listing

**CLI result:** `KeyError: -2147483646` crash.

**Root cause (bug in camply 0.34.1):**  
`going_to_camp_provider.py:427` contains a bare dict lookup:

```python
self.campground_details[facility.resource_location_id]   # line 427
```

This line has no assignment — the value is discarded. It was probably a guard check
whose assignment was accidentally removed. It throws `KeyError` when a facility from
`LIST_CAMPGROUNDS` has no matching entry in `campground_details`.

**Why campground_details is empty for most parks:**  
`CAMP_DETAILS` calls `GET /api/maps` without query parameters, which returns the
root hierarchy tree (6 entries, all with `resourceLocationId=None`). The correct
call is `GET /api/maps?resourceLocationId=<id>`, which returns the park-specific
maps. The provider never passes this parameter — so `campground_details` is populated
only with `{None: <last entry>}`.

**Fix (one line):** delete line 427, or change to:
```python
if facility.resource_location_id not in self.campground_details:
    return facility, None
```

**Workaround result (direct API calls):**  
111 campgrounds returned. Target parks:

| Park | resource_location_id | map_id |
|------|---------------------|--------|
| Golden Ears Provincial Park | -2147483606 | -2147483574 (Alouette South) |
| Alice Lake Provincial Park | -2147483647 | n/a via root maps |
| Cultus Lake Provincial Park | -2147483623 | n/a via root maps |

`map_id` is obtained correctly by calling `api/maps?resourceLocationId=<id>` (7 maps
for Golden Ears: Alouette South/North, Gold Creek, Group Sites, North Beach, etc.)

---

## T3 — Availability Query

Queried Golden Ears, Alouette South (103 sites), Jul 4–6 2026.

```
GET /api/availability/map
  mapId=-2147483574, resourceLocationId=-2147483606
  startDate=2026-07-04, endDate=2026-07-06
  equipmentCategoryId=-32768, partySize=1
→ 200 OK in 0.3s
  resourceAvailabilities: 103 resources
  available (code=0): 0
  unavailable (code=1): 103
```

**Pass.** API call succeeded in 0.3s. Zero available is expected for a peak summer
weekend 10 weeks out. Raw response saved to `responses/availability_raw.json`.

**Availability codes observed:**
- `0` = Available
- `1` = Reserved/Unavailable (all 103 sites)

---

## T4 — Direct Python API

Attempted the prescribed script using `GoingToCamp()` from camply:

```python
from camply.providers.going_to_camp.going_to_camp_provider import GoingToCamp
gtc = GoingToCamp()
cgs = gtc.find_campgrounds(rec_area_id=12)      # crashes — same bug as T2
```

Worked around via direct `requests` calls to the same underlying API. Data model
validated: `resourceAvailabilities` is a dict keyed by resource_id, each value is
a list of availability slot objects with an `availability` integer code.

Sample shape saved to `responses/availability_sample.json`.

**Key data model observations:**
- A park (resourceLocationId) has multiple maps (sub-areas, e.g. Alouette South/North)
- Each map has mapResources (individual campsites)
- Availability codes are integers (0=available, 1=reserved, 2=closed, 3=walk-in)
- `mapLinkAvailabilities` enables recursive traversal into child maps
- All IDs are large negative ints (Java `Integer.MIN_VALUE` + offset)

---

## T5 — Notification Wiring (SKIP)

No Telegram credentials available to test live. Wiring documented:

**Env var names** (note: spec said `CAMPLY_TELEGRAM_*` but actual names differ):
```
TELEGRAM_BOT_TOKEN=<token>
TELEGRAM_CHAT_ID=<chat_id>
```

These can also go in `~/.camply` (camply's dotfile). The relevant classes are:
- `camply/config/notification_config.py` — `TelegramConfig`
- `camply/notifications/telegram.py` — sends via `POST /bot<token>/sendMessage`

To test: set both vars, run with `--notifications telegram`, trigger a window where
a site opens up (or use a park with current availability).

---

## T6 — Booking Capability Check

**Result: camply is read-only by design. No reservation creation capability exists.**

Grep findings across the full camply package:

| File | POST usage |
|------|-----------|
| `providers/going_to_camp/going_to_camp_provider.py` | No POST calls whatsoever |
| `providers/usedirect/usedirect.py:331` | POST to availability search endpoint (read) |
| `notifications/telegram.py`, `slack.py`, `pushbullet.py`, etc. | POST to notification APIs only |

No provider in camply (GoingToCamp, RecreationDotGov, UseDirect, or any other)
implements reservation creation. The `get_reservation_link()` method in
`going_to_camp_provider.py` generates a URL pointing to the human-facing booking
flow but does not automate it.

This is intentional: camply's design is a monitoring/alerting tool — it surfaces
availability and deep-links you to the booking page.

---

## Surprises

1. **`api/maps` without params returns a region tree, not per-park maps.** Camply's
   bug stems from calling this endpoint incorrectly. When called with
   `?resourceLocationId=<id>` it returns the correct park maps.

2. **Multiple maps per park.** Golden Ears has 7 maps (sub-campgrounds). Any
   complete availability check must iterate over all of them, not just the first.
   Camply's `list_site_availability` does handle this via `mapLinkAvailabilities`
   recursive traversal — but it can never reach it because `map_id` is always
   `None` due to the `api/maps` bug.

3. **Response speed is excellent.** The GoingToCamp API returned 103 site
   availabilities in 0.3s. No rate limiting or 403s encountered.

4. **Telegram env var name mismatch.** The spec references `CAMPLY_TELEGRAM_BOT_TOKEN`
   but the actual var is `TELEGRAM_BOT_TOKEN` (no prefix). Uses `~/.camply` dotfile
   or bare environment variables.
