## Why

Every HTTP call to BC Parks fires back-to-back. `search.run()` fans out across parks × maps × windows with zero pause between requests — impolite to the upstream service and a rate-limit risk (the API already returns 403/429, mapped to `RateLimited`). No global throttle exists.

A respectful delay between requests is a **global** concern, not per-profile: future multi-profile support must not let one profile hammer the API. So the value lives in the DB settings table (one global value), not in `profile.json`.

## What Changes

- Add a global, DB-backed **minimum interval between HTTP requests** to BC Parks. Default 5.0 seconds.
- Throttle at the single choke point: `BCParksClient._get()` (api.py). Covers `list_parks`, `list_maps`, `map_availability` everywhere — CLI and daemon alike.
- Delay applies **between** requests, not before the first (monotonic-clock gap tracking; first request pays nothing).
- `BCParksClient.__init__` gains `min_interval_secs: float` and an injectable `sleep` callable (default `time.sleep`) for testability.
- Composition roots read the setting and inject it: `cli.py api_call()` and `daemon.py run_forever()`.
- New `config` CLI group: `campcli config set-interval <secs>` and `campcli config show`. Rejects `<= 0` (exit code 1).
- New setting key `request_interval_secs` (string float in the existing `settings` table).
- New constant `DEFAULT_REQUEST_INTERVAL_SECS = 5.0`.
- Daemon reads the setting **once at startup**; changing it needs a daemon restart. CLI reads fresh per invocation.

Not in scope: live re-read mid-daemon-loop. The existing `daemon --interval` flag (sleep between whole poll cycles, default 1.0s) is a separate knob — left untouched. `interval=0` disables throttling (escape hatch).

## Capabilities

### New Capabilities

- `request-throttle`: A global, DB-backed minimum delay between HTTP requests to BC Parks, set via CLI, applied at the API adapter choke point. Default 5s, configurable, restart-to-apply for the daemon.

### Modified Capabilities

(none — no existing spec governs HTTP request pacing)

## Impact

- **New**: `config` Typer group in `cli.py` (`set-interval`, `show`); `DEFAULT_REQUEST_INTERVAL_SECS` constant; tests for throttle + CLI + store round-trip.
- **Modified**: `infrastructure/api.py` (`BCParksClient.__init__` gains `min_interval_secs` + `sleep`; `_get` throttles); `composition/cli.py` (`api_call()` reads setting, injects interval); `composition/daemon.py` (`run_forever()` reads setting, injects interval).
- **Config**: setting key `request_interval_secs` in the `settings` table (default applied when unset/unparseable).
- **Backward compatible**: unset setting → 5.0s default. No schema migration (settings table already exists).
