# campcli

A CLI + daemon for finding available BC Parks campsites near home, watching for
openings, and tracking bookings. Targets the public BC Parks reservation API.

## Project memory (OKF)

This project uses an [OKF](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md)
knowledge bundle under `memory/` — one markdown concept per file, each with
`type` in YAML frontmatter. The shared system of record for durable project
knowledge (decisions, facts, constraints, gotchas).

**On session start:** read `memory/index.md` for the concept map, then any
concept files relevant to your task. All agents (Claude Code, opencode) read
the same content from this single canonical file.

**Maintenance:** one concept per file. Cross-link with relative markdown links.
Update `memory/index.md` when adding a concept. Curate — don't hoard.

## Core rules

### Toolchain
- **Language:** Python ≥3.12
- **Package manager:** `uv` (see `uv.lock`)
- **Build:** `hatchling` via `pyproject.toml`
- **Run tests:** `uv run pytest`
- **Type check:** `uv run mypy`
- **Lint:** `uv run ruff check`

### Commands
```bash
uv run pytest                          # all tests
uv run pytest tests/test_foo.py        # single file
uv run mypy                            # type check
uv run ruff check                      # lint
uv run campcli --help                  # CLI usage
```

### Secrets and data
- API keys, Telegram tokens, home address → `.env` (never commit)
- BC Parks API: `https://camping.bcparks.ca` (public, no auth)
- Drive-time cache: built offline via `parks drive-times`, loaded at
  composition root

### Conventions
- **Domain language** — use the glossary in `CONTEXT.md`. Key terms: **Park**
  (not campground), **Map** (not zone/loop), **AvailableSite**, **Profile**,
  **WeekendMatch**, **NotInterested**, **DriveTimes**. Watches and Bookings are
  **DEPRECATED** (ADR-0011).
- **Architecture** — Clean Architecture: `domain/` → `application/` →
  `infrastructure/` + `presentation/`, wired through `composition/`. ADRs in
  `docs/adr/`. Ports live in `domain/ports.py`; fakes appear in `conftest.py`.
- **Commits** — Conventional Commits (`feat:`, `fix:`, `refactor:`, `docs:`,
  `chore:`)
- **Dependencies** — ask before adding new ones (uv.lock is tracked)

### Repo layout
```
├── src/campcli/
│   ├── domain/           # Enterprise + application business rules
│   ├── application/      # Use cases, search, command routing
│   ├── infrastructure/   # API client, store, clock, telegram, drive times
│   ├── presentation/     # Formatting / output
│   └── composition/      # CLI + daemon composition roots
├── tests/                # pytest (fakes in conftest.py)
├── docs/adr/             # Architecture Decision Records (12 ADRs)
├── memory/               # OKF knowledge bundle
├── contrib/              # systemd service, helpers
├── responses/            # Sample API responses
├── demos/                # Design proposals
├── CONTEXT.md            # Domain language glossary
├── pyproject.toml        # Metadata, deps, tool config
└── uv.lock               # Lockfile
```

## OKF concepts

| Link | What |
|------|------|
| [index](memory/index.md) | Full concept map — all memory/* files |
