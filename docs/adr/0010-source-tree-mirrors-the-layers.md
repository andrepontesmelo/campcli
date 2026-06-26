# Source tree mirrors the Clean Architecture layers

The 9 prior ADRs describe the codebase in Clean Architecture terms — Domain,
Application, Infrastructure, Presentation, composition root — but the source
tree was one flat `src/campcli/` directory, making the layering
convention-only. This ADR makes the layering structural by moving each module
into a layer folder.

## Folders

- `domain/` — `models.py`, `ports.py`
- `application/` — use-case functions and value objects (`_helpers.py`,
  `availability.py`, `booking_links.py`, `catalog.py`, `command_responses.py`,
  `command_router.py`, `daemon_log.py`, `filters.py`,
  `migrate_profile.py`, `not_interested.py`, `notification_policy.py`,
  `pricing.py`, `profile.py`, `search.py`, `search_loop.py`,
  `search_notifier.py`, `telegram_settings.py`, `telegram_users.py`,
  `throttle.py`)
- `infrastructure/` — adapters (`api.py`, `clock.py`, `drive_times_cache.py`,
  `store.py`, `telegram.py`)
- `presentation/` — `format.py`
- `composition/` — wiring roots (`cli.py`, `daemon.py`) and per-command
  wiring in the `cli_commands/` subfolder
- `constants.py` stays at the top level (shared by all layers)

The dependency rule is now structural: a module in `domain/` imports nothing
from the project. A module in `application/` imports only from `domain/` and
`constants`. A module in `infrastructure/` imports from `domain/`, `application/`,
and `constants` (dependencies point inward). `presentation/` imports from
`domain/`, `application/`, and `constants`. `composition/` imports from all
layers and wires concrete adapters.

## Supersedes ADR-0002's literal file list

ADR-0002 ("Composition root limited to `cli.py` and `daemon.py`") listed the
two entry-point files by name. The composition root is now the `composition/`
folder; `grep -rn 'BCParksClient(' src/campcli/composition'` still shows every
wiring site. The grep-for-concrete-adapter-imports property is preserved.

## Non-goal

No logic changes, no API changes, no test changes beyond import path updates.
