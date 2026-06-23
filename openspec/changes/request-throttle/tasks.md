## 1. Constant + setting helper

- [ ] 1.1 Add `DEFAULT_REQUEST_INTERVAL_SECS = 5.0` to `constants.py`
- [ ] 1.2 Add a helper to read `request_interval_secs` from a `SettingsRepo` and parse to float, returning `DEFAULT_REQUEST_INTERVAL_SECS` when unset or unparseable (one parser, DRY — both composition roots call it)

## 2. Throttle the API adapter

- [ ] 2.1 `BCParksClient.__init__`: add params `min_interval_secs: float = DEFAULT_REQUEST_INTERVAL_SECS` and `sleep: Callable[[float], None] = time.sleep`; store both; init `self._last_request_at: float | None = None`
- [ ] 2.2 In `_get`, before firing the request: if `_last_request_at is not None` and `min_interval_secs > 0`, compute `wait = min_interval_secs - (monotonic() - _last_request_at)` and `sleep(wait)` when `wait > 0`
- [ ] 2.3 After the wait (skip on first call), set `self._last_request_at = monotonic()`; ensure first call never sleeps
- [ ] 2.4 Add `import time` / `from time import monotonic` and `Callable` typing as needed

## 3. Inject at composition roots

- [ ] 3.1 `cli.py api_call()`: build/obtain `SqliteStore(DB_PATH)`, read interval via the helper, pass `min_interval_secs=` into `BCParksClient(...)`
- [ ] 3.2 `daemon.py run_forever()`: read interval via the helper once at startup, pass into `BCParksClient(...)`

## 4. CLI config group

- [ ] 4.1 Add a `config` Typer sub-app, registered on the main app
- [ ] 4.2 `config set-interval <secs: float>`: reject `<= 0` with stderr error + `Exit(code=1)`; else `set_setting("request_interval_secs", str(float(secs)))` and echo confirmation
- [ ] 4.3 `config show`: read setting; print current value, or print default and mark as default when unset

## 5. Tests

- [ ] 5.1 Store round-trip test: `set_setting`/`get_setting` for `request_interval_secs`
- [ ] 5.2 Throttle test: fake `sleep` + stub httpx; first `_get` no sleep, subsequent sleep ≈ interval, `interval=0` never sleeps
- [ ] 5.3 Setting-helper test: unset → default, unparseable → default, valid → parsed float
- [ ] 5.4 CLI test: `config set-interval` writes setting; `config show` reads it back; `set-interval 0` exits 1 and leaves setting unchanged
- [ ] 5.5 Run full suite (`pytest`) and type check (`mypy`) — fix all failures
