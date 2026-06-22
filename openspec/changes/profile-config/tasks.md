## 1. Profile model and loader

- [ ] 1.1 Create `src/campcli/application/profile.py` with `Profile` Pydantic model, `AllowedEntry` model, pattern parser (`parse_pattern`), and `load_profile(catalog_parks)` function
- [ ] 1.2 `parse_pattern(s: str) -> tuple[int, int]`: parse `"fri-sun"` → `(4, 3)` with validation
- [ ] 1.3 `load_profile` reads `profile.json`, validates with Pydantic, resolves `allowed` names to park_id/map_id against catalog list, generates default file if missing
- [ ] 1.4 Add `PROFILE_PATH` constant to `constants.py`, add `fromisoformat` import for date parsing

## 2. Wire profile into search

- [ ] 2.1 Update `expand_windows()` to accept `min_start: date | None` parameter instead of using `PERSONAL_MIN_START_DATE`
- [ ] 2.2 Update `search.run()` to accept `allowed_park_ids: dict[int, set[int] | None] | None` parameter, pre-filter parks and maps
- [ ] 2.3 Remove `build_profile()` from `search.py`
- [ ] 2.4 Update `search.py` imports: remove `DEFAULT_PROFILE`, `PERSONAL_MIN_START_DATE`; add `Profile` type

## 3. Wire profile into notification

- [ ] 3.1 Update `NotificationPolicy.__init__` to accept `rest_days: int = 14`, store as instance attribute
- [ ] 3.2 Update `NotificationPolicy.decide()` to pass `self._rest_days` to `is_too_close()` call
- [ ] 3.3 Update `SearchNotifier.__init__` to accept `rest_days: int = 14`, pass to `NotificationPolicy`
- [ ] 3.4 Remove `REST_DAYS` from `filters.py` (keep `is_too_close` signature, default now unused)

## 4. Wire profile into CLI

- [ ] 4.1 Update `cli.py` `search` command: load profile, override with `--months`/`--distance` flags, pass to `search.run()`
- [ ] 4.2 Handle `--distance` override for `max_drive_hours` in profile
- [ ] 4.3 Remove unused `search.build_profile` call

## 5. Wire profile into daemon

- [ ] 5.1 Update `daemon.py` `run_forever()`: load profile from file, pass to `Poller` as dict (or convert Profile to dict for Poller compatibility)
- [ ] 5.2 Update `Poller.__init__` to accept `rest_days: int` parameter, pass to `SearchNotifier`
- [ ] 5.3 Update `Poller` to use profile `allowed_park_ids` when calling `run_search`

## 6. Cleanup dead code

- [ ] 6.1 Remove `DEFAULT_PROFILE` from `constants.py`
- [ ] 6.2 Remove `PERSONAL_MIN_START_DATE` from `constants.py`
- [ ] 6.3 Remove unused `FRIDAY`, `SATURDAY` imports from `constants.py` if no longer needed
- [ ] 6.4 Remove `build_profile()` from `search.py` exports (if referenced elsewhere)

## 7. Update and run tests

- [ ] 7.1 Add unit tests for `parse_pattern()` in new test file
- [ ] 7.2 Add unit tests for `Profile` model validation
- [ ] 7.3 Add unit tests for `load_profile()` (file missing, invalid JSON, bad schema, unknown names)
- [ ] 7.4 Update `test_search.py` to use Profile instead of dict
- [ ] 7.5 Update `test_poller.py` to use Profile-compatible test fixtures
- [ ] 7.6 Update `test_notification_policy.py` for rest_days parameter
- [ ] 7.7 Add tests for `allowed` filtering in `search.run()`
- [ ] 7.8 Run full test suite (`pytest`)
- [ ] 7.9 Run mypy type checking
