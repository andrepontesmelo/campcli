# campcli

A CLI + daemon for finding available BC Parks campsites near home, watching for openings, and tracking bookings.

## Language

**Park**:
A bookable BC Parks campground — reference data (id, name, region), no state.
_Avoid_: campground, location, site

**Map**:
A sub-area of a Park (a loop or zone) that holds individual sites.
_Avoid_: zone, area, loop

**AvailableSite**:
A specific site found open for a concrete date range during an availability query.
_Avoid_: opening, vacancy, slot

**Watch**:
A persisted standing query — a Park + date range the user wants re-checked on demand.

**Booking**:
A campsite reservation the user has already made, recorded for trip planning.
_Avoid_: reservation, trip

**BlockedPark**:
A Park the user never wants to be notified about.
_Avoid_: blacklist entry, excluded park

**WeekendMatch**:
An availability hit produced by `search` — a (Park, Map, weekend window) with a count of open sites.
_Avoid_: result, hit

**Profile**:
The search preferences — weekend patterns, horizon in months, max drive hours.

**DriveTimes**:
A read-only value object over geocoded driving durations from home to each Park; the seam for drive-time data. Application and Presentation receive it instead of reading the JSON cache.
_Avoid_: drive cache, drive_cache dict

## Relationships

- A **Park** has one or more **Maps**; a **Map** holds **AvailableSites**
- A **Watch** names a **Park** and a date range; running it yields **AvailableSites**
- `search` expands a **Profile** into weekend windows and produces **WeekendMatches**
- **DriveTimes** is keyed by **Park** id; `search` and the parks listing filter **Parks** through it
- A **BlockedPark** suppresses **WeekendMatch** notifications for that **Park**

## Example dialogue

> **Dev:** "When `search` filters **Parks** by distance, does it hit the network?"
> **Domain expert:** "No — distance comes from **DriveTimes**, which is built offline by `parks drive-times` and loaded once at the composition root. `search` just receives the value object."
