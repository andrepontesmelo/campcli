# profile-config Specification

## Purpose
TBD - created by archiving change profile-config. Update Purpose after archive.
## Requirements
### Requirement: Profile is loaded from a JSON file
The system SHALL load the search profile from `~/.campcli/profile.json` at startup.
If the file does not exist, the system SHALL generate it with sensible defaults
and then load it.

#### Scenario: File exists and is valid
- **WHEN** `profile.json` exists and contains valid JSON matching the Profile schema
- **THEN** the system loads it and uses its values for all search/notification behaviour

#### Scenario: File missing on first run
- **WHEN** `profile.json` does not exist
- **THEN** the system generates a default `profile.json`, writes it to disk, and loads it

#### Scenario: File contains invalid JSON
- **WHEN** `profile.json` exists but is not valid JSON
- **THEN** the system exits with a non-zero code and a descriptive error message

#### Scenario: File fails schema validation
- **WHEN** `profile.json` exists but contains values that do not match the Profile schema (e.g. non-integer `max_horizon_months`)
- **THEN** the system exits with a non-zero code and a descriptive error message naming the offending field

### Requirement: Profile fields
The Profile model SHALL contain the following fields:

| Field | Type | Default | Description |
|---|---|---|---|
| `patterns` | `list[str]` | `["fri-sun"]` | Weekend patterns in `day-day` format |
| `max_horizon_months` | `int` | `3` | How far ahead to search (months) |
| `max_drive_hours` | `float` | `3.0` | Maximum driving time from home |
| `min_start_date` | `str \| null` | `null` | ISO date floor for windows; null = today |
| `rest_days_between_bookings` | `int` | `14` | Minimum gap in days between bookings; 0 = disabled |
| `allowed` | `list[object]` | `[]` | Park/map whitelist; empty = all parks allowed |

Each `allowed` entry SHALL be an object with `park` (string, required) and optionally `map` (string or null).

#### Scenario: Default profile is generated
- **WHEN** the system generates a default `profile.json`
- **THEN** it writes the defaults shown in the table above, with `allowed` as an empty list

### Requirement: Human-friendly pattern format
Patterns SHALL be written as `"day-day"` strings (e.g. `"fri-sun"`, `"sat-sun"`).
The system SHALL parse the start day and compute nights as `(end_weekday - start_weekday + 1)` within a 7-day week.
The system SHALL accept: `mon`, `tue`, `wed`, `thu`, `fri`, `sat`, `sun` (case-insensitive).
For a two-day pattern `fri-sun`: Friday=4, Sunday=6, nights=3 (Fri, Sat, Sun checked out Monday).

#### Scenario: Parse fri-sun
- **WHEN** the pattern string is `"fri-sun"`
- **THEN** the system resolves it to weekday 4 (Friday), nights 3

#### Scenario: Parse sat-sun
- **WHEN** the pattern string is `"sat-sun"`
- **THEN** the system resolves it to weekday 5 (Saturday), nights 2

#### Scenario: Invalid pattern rejects
- **WHEN** the pattern string is `"xyz-sun"` or `"fri"` (no hyphen)
- **THEN** the system exits with an error at profile load time

### Requirement: Pattern `fri-sun` means 3 nights (Fri, Sat, Sun)
The string `"fri-sun"` SHALL produce 3 nights — Friday arrival, departing Monday. The original code used `(FRIDAY, 2)` for Fri-Sat (2 nights). The user's intent is Fri+Sat+Sun = 3 nights so `"fri-sun"` = Friday start, 3 nights.

#### Scenario: fri-sun is 3 nights
- **WHEN** profile has `patterns: ["fri-sun"]`
- **THEN** `expand_windows` produces windows with `(start_date, 3)` for each Friday in the horizon

### Requirement: min_start_date controls the search window floor
When `min_start_date` is `null`, `expand_windows` SHALL use today's date as the earliest window start (no artificial floor).
When `min_start_date` is an ISO date string, `expand_windows` SHALL skip windows starting before that date.

#### Scenario: null min_start_date uses today
- **WHEN** `min_start_date` is `null` and today is June 22, 2026
- **THEN** windows starting June 22, 2026 or later are included

#### Scenario: explicit min_start_date skips earlier
- **WHEN** `min_start_date` is `"2026-08-01"`
- **THEN** windows starting before August 1, 2026 are excluded

### Requirement: rest_days_between_bookings controls notification suppression
`NotificationPolicy` SHALL accept a `rest_days` parameter.
When `rest_days_between_bookings` is `0`, no match SHALL be suppressed due to booking proximity.
When `rest_days_between_bookings` is `14` (default), matches within 14 days of any booking SHALL be suppressed.

#### Scenario: rest_days=0 disables suppression
- **WHEN** `rest_days_between_bookings` is `0` and a booking starts on the same date as a match
- **THEN** the match is NOT suppressed (since 0 < 0 is False)

#### Scenario: rest_days=14 with nearby booking
- **WHEN** `rest_days_between_bookings` is `14`, a booking starts August 28, and a match starts August 15 (13 days gap)
- **THEN** the match is suppressed

### Requirement: Allowed parks/maps whitelist
When `allowed` is non-empty, `search.run()` SHALL only check parks whose name matches an `allowed` entry.
If an `allowed` entry specifies `map`, only that specific map SHALL be checked within the park.
If an `allowed` entry omits `map` (or it is `null`), all maps in the park SHALL be checked.
When `allowed` is empty, all parks SHALL be checked (current behaviour).
Resolution SHALL happen at profile load time using the park catalog.

#### Scenario: Single park with specific map
- **WHEN** `allowed` is `[{"park": "Cultus Lake", "map": "Maple Bay"}]`
- **THEN** only Cultus Lake park is searched, and only its Maple Bay map is checked

#### Scenario: Single park without map
- **WHEN** `allowed` is `[{"park": "Golden Ears"}]`
- **THEN** all Golden Ears maps (except walk-ins) are checked

#### Scenario: Empty allowed list
- **WHEN** `allowed` is `[]`
- **THEN** all parks within drive-time range are searched (current behaviour)

#### Scenario: Unknown park name
- **WHEN** `allowed` contains a park name that does not match any park in the catalog
- **THEN** the system exits with an error at profile load time

#### Scenario: Unknown map name
- **WHEN** `allowed` specifies a map name that does not exist in the matched park
- **THEN** the system exits with an error at profile load time

### Requirement: CLI search uses profile.json
The `search` command SHALL read the profile from `profile.json`.
CLI flags `--months` and `--distance` SHALL override the corresponding profile fields at runtime.

#### Scenario: CLI overrides profile
- **WHEN** `profile.json` has `max_drive_hours: 3.0` and user passes `--distance 5h`
- **THEN** the search uses `max_drive_hours: 5.0`

### Requirement: Daemon uses profile.json
The daemon SHALL load the profile once at startup from `profile.json` and reuse it for every poll cycle.
The profile SHALL NOT be auto-reloaded while the daemon is running.

#### Scenario: Daemon starts with profile
- **WHEN** the daemon starts and `profile.json` exists
- **THEN** it loads the profile and uses it for all poll ticks

#### Scenario: Daemon ignores file changes
- **WHEN** the daemon is running and `profile.json` is edited on disk
- **THEN** the running daemon continues using the profile snapshot loaded at startup

### Requirement: Profile file location follows existing conventions
The profile file SHALL be stored at `CONFIG_DIR / "profile.json"` (i.e. `~/.campcli/profile.json`), matching the pattern used by `catalog.json` and `drive_times.json`.

#### Scenario: Config directory created
- **WHEN** `~/.campcli/` does not exist
- **THEN** the system creates it before writing `profile.json`

