# Poller Split Demo

**Shipped**: The monolithic `Poller` class (398 lines, 8 dependencies) is dissolved.
Three focused modules now handle search, command responses, and Telegram settings.
No user-facing behavior changed — the daemon starts the same way, polls the same way,
and responds to commands the same way.

**Replaces**: `src/campcli/application/poller.py` (deleted). The `Poller` class no longer exists.

**Internal**: `poller.py` split into `search_loop.py`, `command_responses.py`, and
`telegram_settings.py`. `composition/daemon.py` wires them directly instead of
instantiating a single Poller object.

---

## Prerequisites

```bash
git clone https://github.com/your-org/campcli.git
cd campcli
PYTHONPATH=src python3 -m pip install -e ".[dev]"
```

## Step 1: Verify the daemon imports cleanly

```bash
PYTHONPATH=src python3 -c "from campcli.composition.daemon import run_forever, startup; print('daemon imports OK')"
```

**Expected output**:
```
daemon imports OK
```

No import errors, no `ModuleNotFoundError` for the deleted `poller.py`.

## Step 2: Verify the three new modules import cleanly

```bash
PYTHONPATH=src python3 -c "
from campcli.application.search_loop import run_search_once
from campcli.application.command_responses import handle_commands_forever, process_update
from campcli.application.telegram_settings import get_verbose, set_verbose, get_chat_id
print('All application modules OK')
"
```

**Expected output**:
```
All application modules OK
```

## Step 3: Confirm poller.py is gone

```bash
test -f src/campcli/application/poller.py && echo "STILL EXISTS (unexpected)" || echo "DELETED (expected)"
```

**Expected output**:
```
DELETED (expected)
```

## Step 4: Run the full test suite

```bash
PYTHONPATH=src python3 -m pytest tests/ -q --tb=short
```

**Expected output** (tail):
```
... 291 passed, 11 errors in ~3s
```

The 11 errors are all in `tests/test_telegram.py` (missing `httpx_mock` fixture —
a pre-existing issue unrelated to this feature). All poller-split tests (67 across
`test_search_loop.py`, `test_command_responses.py`, `test_telegram_settings.py`,
`test_daemon.py`, `test_poller.py`, `test_command_router.py`) pass.

## Step 5: Check for remaining Poller references

```bash
rg -c Poller src/ --no-filename | awk -F: '{sum+=$2} END {print sum, "Poller mentions (all docstrings/comments)"}'
```

**Expected output**: `7 Poller mentions (all docstrings/comments)` — zero live
code references. The `Poller` class is fully dissolved.

## Step 6: Start the daemon (requires bot token)

```bash
# Requires a real bot token. Unset CAMPCLI_BOT_TOKEN skips Telegram,
# and the daemon will run in CLI-only mode.
CAMPCLI_BOT_TOKEN="" PYTHONPATH=src python3 -m campcli.cli daemon
```

The daemon starts, prints `campcli daemon started v3` to any known chat, and begins
polling. Press Ctrl-C to stop. If no bot token, it fails fast with a clear error —
no change from before the split.
