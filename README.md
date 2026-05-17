# campcli

Command-line tool for monitoring [BC Parks](https://camping.bcparks.ca/) campsite
availability. Search by drive time from a home base, watch parks for openings, and
get Telegram notifications when new sites appear.

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (recommended) — manages the virtualenv and
  dependencies for you, so **no manual `venv` step is needed**.

## Run it

### With uv (recommended)

`uv run` creates and manages the virtualenv automatically:

```sh
uv run campcli --help
uv run campcli doctor          # check local setup
```

To install `campcli` as a global command:

```sh
uv tool install .
campcli --help
```

### Without uv

Create a virtualenv yourself and install the project into it:

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
campcli --help
```

> Note: `requirements.txt` in the repo is unrelated leftover dependencies — do not
> use it. The real dependencies are declared in `pyproject.toml`.

## Common commands

```sh
campcli doctor                 # verify setup and cached data
campcli catalog ...            # build/refresh the cached park catalog
campcli parks ...              # discover parks and sub-areas (maps)
campcli check --park "<name>" --start YYYY-MM-DD
campcli search --start YYYY-MM-DD --max-drive 3h30m
campcli watch ...              # manage persistent availability watches
campcli book ...               # booking deep-link helpers
campcli blocked ...            # manage the blocklist of unwanted parks
```

Every command and sub-command supports `--help`.

## Telegram daemon (optional)

A long-running poller can send Telegram notifications when new campsites appear.
It needs `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in the environment:

```sh
TELEGRAM_BOT_TOKEN=... TELEGRAM_CHAT_ID=... campcli daemon
```

To run it as a per-user systemd service, see [`contrib/README.md`](contrib/README.md).

## Development

```sh
uv run pytest                  # run tests
uv run mypy                    # type-check
```

## License

See [LICENSE](LICENSE).
