# Next Steps

## What camply gives you for free

- **Availability polling loop** (`--search-forever`) with configurable sleep interval
- **Multi-park / multi-date fan-out** — query many parks/dates in one run
- **Notification integrations** — Telegram, Slack, email, Pushover, Pushbullet,
  ntfy, webhook; all battle-tested
- **Recreation area / campground discovery** (once the `api/maps` bug is fixed)
- **Booking deep-link generation** — `get_reservation_link()` produces a
  pre-filled URL that drops the user into the checkout flow
- **Rate-limit wrapper** — `ratelimit` + `tenacity` retry baked in via base provider

## What you'd need to build

### (a) Cancellation monitoring beyond camply's notify

camply today: sends one alert per available site found per polling interval,
then re-alerts on the next poll if still available. It does **not**:

- Track state across runs (no persistence layer — each run is stateless)
- Distinguish "newly opened" from "still open from last check"
- Suppress duplicate alerts for the same site across multiple polls

**What to build:**

1. **State store** — a small SQLite or JSON file tracking `{resource_id: first_seen_ts}`.
   On each poll, compare current availability against the store:
   - new site (not in store) → alert + record
   - site still open → suppress alert (or send reminder after N hours)
   - site disappeared → remove from store (someone booked it)

2. **Alert deduplication key** — `(resource_location_id, map_id, resource_id, start_date)`.
   camply's `AvailableResource` has `resource_id` and `map_id`; you'd add `start_date`.

3. **Hook point** — override or wrap `list_site_availability` to intercept results
   before they reach the notifier, or subclass `BaseNotifier`.

Effort: ~200 lines Python, no external dependencies beyond what camply already installs.

### (b) Automated reservation flow

camply has no booking capability. The GoingToCamp booking flow is a multi-step
web form with CSRF tokens and session state. Automation options, in increasing effort:

**Option 1 — Browser automation (Playwright/Selenium)**  
Drive the existing `https://camping.bcparks.ca/create-booking/results?...` URL
that `get_reservation_link()` already constructs. Fill the form programmatically.

Risks:
- GoingToCamp likely has bot detection (Cloudflare or similar) on the checkout path
- Form steps: equipment selection → site selection → party details → payment
- Payment step requires real credit card input — must be handled carefully
- Session cookies required; can't be done with `requests` alone

**Option 2 — Reverse-engineer the booking API**  
The GoingToCamp API (`/api/reservation` or similar) likely exists behind the same
domain. Inspect traffic from the browser during a real booking to find the
`POST /api/...` endpoints and their payloads. Then replicate with `requests`.

Risks:
- BC Parks ToS almost certainly prohibits automated reservation creation
- API may require a session token tied to an authenticated account
- CSRF tokens regenerate per-session
- If the API changes, your automation breaks silently

**Option 3 — Human-in-the-loop hybrid (recommended)**  
Use camply for monitoring. When a site opens up, send a Telegram alert with the
deep-link URL already constructed. Human clicks the link and completes booking
in <60s. This respects ToS, avoids bot detection, and handles the payment step safely.

**Recommendation:**  
Build option (a) — stateful cancellation tracking — first. It solves the real
problem (getting notified once, not spammed) with low risk and low effort.
Hold off on (b) until you've confirmed that manual booking via the deep-link is
actually too slow in practice.

## Immediate action items

1. **Fix or patch the camply `api/maps` bug** before depending on the CLI.
   One-liner patch: delete `going_to_camp_provider.py:427`.
   File a bug upstream at https://github.com/juftin/camply.

2. **Iterate over all maps per park** in your availability check — Golden Ears
   has 7 sub-areas; a single `mapId` only covers one campground loop.

3. **Confirm Telegram wiring** with real credentials using env vars
   `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` (not the `CAMPLY_` prefix the docs suggest).
