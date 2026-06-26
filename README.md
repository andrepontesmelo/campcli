# campcli

A CLI + long-running daemon for finding available BC Parks campsites near home,
watching for openings, and tracking bookings. Targets the public BC Parks
reservation API (`camping.bcparks.ca`) and turns it into a scriptable,
notifiable surface — driven from your terminal during planning, and from a
systemd-managed daemon when you want alerts.

## What it does

campcli models BC Parks as **Parks** that contain **Maps** (loops / sub-areas)
holding **AvailableSites**. On top of that it layers:

- **One-shot availability checks** for a park + date range + party size.
- **Pattern-driven weekend search** that expands a **Profile** of
  `weekday-span` patterns (e.g. `fri-sun`, `fri-mon:2-3`) into concrete weekend
  windows across an N-month horizon, filtered by drive-time from home.
- **A daemon** that polls the API on an interval, suppresses duplicates,
  respects a per-profile cooldown between bookings, and sends Telegram alerts
  with a clickable booking deep-link for each new opening.
- **Booking deep-links** — `book open` and `book quote` generate a
  pre-filled URL that drops you straight into the GoingToCamp checkout flow,
  plus an offline fee estimate.
- **Multi-profile** configurations (e.g. one for quick weekend trips, another
  for week-long holidays), each with its own parks, patterns, horizon, drive
  budget, rest days, and Telegram recipients.
- **"Not interested"** suppression scoped to a `(profile, park, date_start,
  date_end)` tuple — tell the daemon you don't want a specific Park on a
  specific weekend without muting it forever.

## Features

- **CLI subcommand groups**
  - `check` — one-shot availability check (`--park`, `--start`, `--nights`,
    `--party-size`, `--map`).
  - `search` — pattern-driven weekend search against the active profile, with
    `--months`, `--distance`, `--group-by park|weekend`, `--with-urls`.
  - `parks list|show|drive-times` — discover parks and their sub-areas; build
    and refresh the local drive-time cache from home to every park.
  - `book open` / `book quote` — generate a deep-link to the GoingToCamp
    booking flow for an availability hit.
  - `catalog refresh` — refresh the local parks/sub-areas catalog.
  - `config set-interval|show` — tune the per-request throttle (seconds
    between API calls).
  - `profile create|list|show|edit|enable|disable|delete|search` plus
    `profile tg-add|tg-rm|tg-list` and `profile not-interested add|rm|list`.
  - `doctor` — verify API reachability and print config paths.
  - `daemon` — run the long-running poller (intended to run under systemd).
- **Daemon**
  - Stateful cancellation tracking — each `(park, map, start_date, nights)`
    tuple is deduped so you get one alert per opening, not one per poll.
  - Per-profile cooldown via `rest_days_between_bookings` so you aren't
    pinged about openings that conflict with a booking you already have.
  - Telegram bot commands (handled in a background thread): per-chat verbose
    logging, recipient registration, etc.
  - Graceful handling of `RateLimited` and `ApiError` with structured exit
    codes.
- **Multi-profile** — each profile owns its own parks list, patterns, horizon,
  drive-time budget, rest-days, and Telegram recipient set; the daemon
  iterates over all enabled profiles per poll cycle.
- **Drive-time filtering** — drive durations are geocoded once into
  `~/.campcli/drive_times.json` (`parks drive-times [--refresh]`) and loaded
  as a read-only `DriveTimes` value object; the rest of the app never reads
  the cache directly.
- **Throttling** — a configurable `request_interval_secs` setting (default
  5.0s) caps outbound API rate.
- **Pattern parsing** — `fri-sun`, `fri-mon`, with optional `:min-max` suffix
  for variable-length stays (e.g. `fri-mon:2-3` = Friday-to-Monday, 2 or 3
  nights).
- **Catalog caching** — parks and maps are cached in
  `~/.campcli/catalog.json` to avoid repeated full-table fetches.

## Install

Requires Python 3.12+.

```sh
# from a clone
git clone <repo> campcli
cd campcli
python -m venv .venv
. .venv/bin/activate
pip install -e .

# or, with uv
uv tool install .
```

This installs a `campcli` console script. Verify with `campcli --help`.

### Telegram setup (for the daemon)

1. Create a bot with [@BotFather](https://t.me/BotFather) and grab the token.
2. DM the bot, then fetch your `chat_id` from
   `https://api.telegram.org/bot<TOKEN>/getUpdates`.
3. Store the env file:
   ```sh
   mkdir -p ~/.config/campcli
   cat > ~/.config/campcli/telegram.env <<EOF
   TELEGRAM_BOT_TOKEN=...
   TELEGRAM_CHAT_ID=...
   EOF
   chmod 600 ~/.config/campcli/telegram.env
   ```

## Run

```sh
campcli doctor                                         # verify API + paths
campcli catalog refresh                                # fetch parks/maps
campcli parks drive-times                              # geocode home→park (slow, one-off)
campcli parks list --distance 3h                      # parks within a 3h drive
campcli check -p 1 -s 2026-07-10 -n 2                 # one-shot availability
campcli search                                         # pattern search, active profile
campcli search --distance 4h --with-urls               # with booking links
campcli book open -p 1 -s 2026-07-10 -n 2              # build a booking URL
campcli book quote -p 1 -s 2026-07-10 -n 2             # estimate the fee

# profiles
campcli profile create weekend --horizon 3 --distance 3
campcli profile edit weekend --add-park "Golden Ears"
campcli profile tg-add weekend 123456789

campcli daemon                                         # long-running poller
```

### Run the daemon under systemd

```sh
mkdir -p ~/.config/systemd/user ~/.local/state/campcli
cp contrib/campcli-daemon.service ~/.config/systemd/user/
loginctl enable-linger $USER                          # survive logout
systemctl --user daemon-reload
systemctl --user enable --now campcli-daemon
journalctl --user -u campcli-daemon -f
```

Adjust `ExecStart=` in the unit if your `campcli` is not on
`~/.local/bin/campcli` (e.g. you installed with `pip install --user` or a
different `uv tool install` location).

## State locations

| Path                                  | Purpose                              |
|---------------------------------------|--------------------------------------|
| `~/.campcli/state.db`                 | SQLite store (profiles, settings, …) |
| `~/.campcli/catalog.json`             | Cached parks + maps                  |
| `~/.campcli/drive_times.json`         | Cached drive-time per park           |
| `~/.campcli/profile.json`            | Legacy profile store (auto-migrated) |

## Development

```sh
pip install -e ".[dev]"
pytest                  # 42 tests
mypy                    # 0 issues
```

The codebase follows Clean Architecture layering (`domain` / `application` /
`infrastructure` / `presentation` / `composition`); see `docs/adr/` for the
recorded decisions and `CONTEXT.md` for the domain language.

## License

See repository.
