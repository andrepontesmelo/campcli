## Context

`BCParksClient._get()` (api.py) is the sole HTTP entry point for the BC Parks API — all three protocol methods route through it. No pacing today. Settings already have a generic k/v home: the `settings` table via `SettingsRepo` (`get_setting`/`set_setting`), same layer (Infrastructure) as the API adapter.

## Decisions

### Throttle location: `_get`, between requests, skip first
Single choke point = uniform coverage with one edit. "Between requests, not before first" via monotonic gap:

```
now = monotonic()
if last is not None:
    wait = interval - (now - last)
    if wait > 0:
        sleep(wait)
last = monotonic()   # after the sleep
# ... fire request ...
```

First call: `last is None` → no sleep. `interval <= 0` → `wait` never positive → no sleep (disabled).

Rationale for re-reading `monotonic()` after sleep rather than `last = now`: anchors the next gap to actual wake time, avoiding drift if `sleep` overshoots.

### Value flow: read at composition root, inject (Q2 = A)
`BCParksClient` stays free of DB coupling. `__init__(min_interval_secs: float, sleep=time.sleep)`. The composition roots own the store and read the setting:

- `cli.py api_call()`: build `SqliteStore(DB_PATH)`, read `request_interval_secs`, parse → float (fallback default), pass to client.
- `daemon.py run_forever()`: same, once at startup.

A small helper reads + parses the setting with the default fallback (defensive: unset OR unparseable → 5.0). Place it where both roots can call it — simplest is a module function in `cli.py` or a tiny helper in `constants.py`/`store`. Implementer picks the lowest-friction spot; keep it DRY (one parser, two callers).

### Setting: `request_interval_secs`, string float
Stored as `str(float)`, e.g. `"5.0"`. Read helper: `float(value)` in try/except → default on failure. Default constant `DEFAULT_REQUEST_INTERVAL_SECS = 5.0` in `constants.py`.

### CLI: `config` group (Q4 = A)
New Typer sub-app `config`:
- `config set-interval <secs: float>` — validate `> 0` else `typer.echo(err) + Exit(1)` (matches `_parse_*_or_exit` pattern). Write `set_setting("request_interval_secs", str(secs))`. Echo confirmation.
- `config show` — read setting; print value or, if unset, print the default and mark it as default.

### Testability: injectable `sleep`
Tests pass a fake `sleep` (records call durations) + a stub httpx client (or monkeypatched `_get` transport). Assert: first call no sleep; subsequent sleep ≈ interval − elapsed; `interval=0` never sleeps. Monotonic stays real; with a fast fake httpx the elapsed gap ≈ 0 so sleep ≈ interval.

## Risks / Trade-offs

- **Daemon restart to apply** (Q6): accepted. Live re-read = scope creep.
- **Per-request, not per-host-burst**: a single `search.run` does many requests; total wall-clock grows ~`requests × interval`. Intended — that is the politeness. Daemon `--interval` tick is independent and additive.
- **Default-on for everyone**: existing CLI users suddenly see 5s spacing. Acceptable (politeness default); `config set-interval 0` opts out.

## Migration

None. `settings` table exists. Unset key → default. No data migration.
