## ADDED Requirements

### Requirement: Minimum interval between HTTP requests
The system SHALL enforce a configurable minimum delay between consecutive HTTP requests to the BC Parks API, applied at the API adapter (`BCParksClient._get`). The delay SHALL apply between requests, not before the first request of a client instance.

#### Scenario: First request is not delayed
- **WHEN** a freshly constructed `BCParksClient` makes its first `_get` call
- **THEN** no sleep occurs before the request

#### Scenario: Subsequent request waits the remaining gap
- **WHEN** a second `_get` call begins less than `min_interval_secs` after the previous request fired
- **THEN** the client sleeps for the remaining time so the gap between requests is at least `min_interval_secs`

#### Scenario: Slow caller pays no extra delay
- **WHEN** a `_get` call begins more than `min_interval_secs` after the previous request
- **THEN** no sleep occurs (the gap is already satisfied)

#### Scenario: Interval of zero disables throttling
- **WHEN** `min_interval_secs` is `0`
- **THEN** no `_get` call ever sleeps

### Requirement: Throttle covers all API methods
The throttle SHALL apply to every BC Parks request type, because all of them route through `_get`: `list_parks` (catalog fetch), `list_maps`, `map_availability`, `resource_details`, and `list_resource_locations`.

#### Scenario: Availability fan-out is paced
- **WHEN** `search.run()` issues many `map_availability` requests in sequence
- **THEN** each consecutive request is separated by at least `min_interval_secs`

### Requirement: Interval is global and DB-backed
The interval SHALL be stored as a single global value in the `settings` table under key `request_interval_secs`, NOT in `profile.json`. This keeps pacing independent of any individual search profile.

#### Scenario: Stored as a string float
- **WHEN** the interval is set to `5.0`
- **THEN** `get_setting("request_interval_secs")` returns `"5.0"`

#### Scenario: Unset key falls back to default
- **WHEN** `request_interval_secs` is not present in the settings table
- **THEN** the system uses the default of 5.0 seconds

#### Scenario: Unparseable value falls back to default
- **WHEN** `request_interval_secs` holds a value that is not a valid float
- **THEN** the system uses the default of 5.0 seconds rather than crashing

### Requirement: Interval is injected at the composition root
The composition roots SHALL read `request_interval_secs` from the store and pass it to `BCParksClient`. The API adapter SHALL NOT read the database itself.

#### Scenario: CLI reads the setting per invocation
- **WHEN** a CLI command builds a `BCParksClient` via `api_call()`
- **THEN** it reads the current `request_interval_secs` value and constructs the client with that interval

#### Scenario: Daemon reads the setting once at startup
- **WHEN** the daemon `run_forever()` builds its `BCParksClient`
- **THEN** it reads `request_interval_secs` once at startup and reuses that interval for the daemon lifetime

#### Scenario: Daemon ignores later changes
- **WHEN** the daemon is running and `request_interval_secs` is changed via the CLI
- **THEN** the running daemon continues using the value read at startup until restarted

### Requirement: CLI config command sets and shows the interval
The system SHALL provide a `config` command group with `set-interval` and `show` subcommands.

#### Scenario: Set a valid interval
- **WHEN** the user runs `campcli config set-interval 8`
- **THEN** the system writes `request_interval_secs = "8.0"` to the settings table and confirms

#### Scenario: Reject zero or negative
- **WHEN** the user runs `campcli config set-interval 0` or a negative value
- **THEN** the system prints an error to stderr and exits with code 1, leaving the setting unchanged

#### Scenario: Show current value
- **WHEN** the user runs `campcli config show` and a value is set
- **THEN** the system prints the current `request_interval_secs`

#### Scenario: Show falls back to default
- **WHEN** the user runs `campcli config show` and no value is set
- **THEN** the system prints the default of 5.0 seconds and indicates it is the default

### Requirement: Injectable sleep for testing
`BCParksClient.__init__` SHALL accept a `sleep` callable defaulting to `time.sleep`, so the throttle can be tested without real waiting.

#### Scenario: Tests assert sleep duration without waiting
- **WHEN** a `BCParksClient` is constructed with a fake `sleep` that records its argument
- **THEN** the recorded durations reflect the throttle behaviour and no real time elapses
