# CLI Use-Case Extract Demo

**Shipped**: All use-case logic extracted from `composition/cli.py` into
`application/` modules grouped by Domain noun (ADR-0005). `cli.py` shrinks from
882 lines to 275. New `composition/cli_commands/` package holds thin Typer
wrappers — each command is a single function call to an application use-case
function. No user-facing behavior changed.

**Replaces**: 33 inline functions in `composition/cli.py` (profile CRUD,
not-interested management, search orchestration, booking helpers) that lived
alongside Typer decorators.

**Internal**: `cli.py` is now ~275 lines of CLI concerns (arg parsing, adapter
construction, error handling). Use cases live in `application/profile.py` (345
lines, Profile domain noun), `application/not_interested.py` (120 lines,
NotInterested domain noun), and `application/search.py` (355 lines, Search
domain noun — extended from the pre-existing search module). CLI command
registration moved to `composition/cli_commands/{profile,parks,book,catalog,config}.py`
using a `_cli` indirection pattern to avoid circular imports.

---

## Prerequisites

```bash
git clone <this-repo> campcli
cd campcli
python3 -m pip install -e ".[dev]"
```

No API keys or Telegram tokens needed — all checks below are local.

## Step 1: Confirm cli.py is under the 300-line target

```bash
wc -l src/campcli/composition/cli.py
```

**Expected output**:
```
275 src/campcli/composition/cli.py
```

## Step 2: Confirm CLI imports cleanly

```bash
PYTHONPATH=src python3 -c "from campcli.composition.cli import app; print('import OK')"
```

**Expected output**:
```
import OK
```

No `ImportError`, no circular import failures.

## Step 3: Verify all sub-command groups register

```bash
campcli --help | head -5
campcli profile --help | head -3
campcli profile not-interested --help | head -3
campcli parks --help | head -3
campcli book --help | head -3
campcli catalog --help | head -3
campcli config --help | head -3
```

**Expected**: every group prints its `Usage:` and command list. No `No such command`
errors for the listed groups.

## Step 4: Run the full test suite

```bash
PYTHONPATH=src python3 -m pytest tests/ -q --tb=short
```

**Expected output** (tail):
```
... 344 passed in ~4s
```

Or with `test_telegram.py` included: 344 passed, 11 errors (known pre-existing
`httpx_mock` fixture issue — unrelated to this feature).

New use-case tests (54 total) all pass:
- `tests/test_profile_use_cases.py` — 30 tests
- `tests/test_not_interested_use_cases.py` — 14 tests
- `tests/test_search_use_cases.py` — 10 tests

## Step 5: Verify no use-case logic remains in cli.py

`cli.py` functions should be limited to CLI infrastructure: arg parsing,
adapter construction, error formatting, and Typer decorators.

```bash
# Count non-trivial functions in cli.py
PYTHONPATH=src python3 -c "
import ast, sys
tree = ast.parse(open('src/campcli/composition/cli.py').read())
funcs = [n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
# Filter: only functions defined directly in cli.py (not typer decorated commands)
non_cmd = [f for f in funcs if not f.startswith('_main')]
print(f'Functions in cli.py: {len(non_cmd)}')
for f in sorted(non_cmd):
    print(f'  {f}')
"
```

**Expected**: Functions like `_parse_hours`, `_parse_date_or_exit`, `_store`,
`api_call`, `_exit_for`, `_run_profile_migration` — all CLI infrastructure.
No `profile_create`, `not_interested_add`, `_search_for_profile`, etc.

## Step 6: Confirm use-case modules are grouped by Domain noun

```bash
# Each application module handles one Domain noun
head -1 src/campcli/application/profile.py
head -1 src/campcli/application/not_interested.py
head -1 src/campcli/application/search.py
```

**Expected**:
```
"""Profile use-case functions — profile CRUD, resolution, and search.
```
```
"""Not-interested use-case functions — add, remove, list skip entries per profile.
```
```
"""Search orchestration for the ``campcli search`` command.
```

## Step 7: Test a use-case function directly (without CLI)

```bash
PYTHONPATH=src python3 -c "
from campcli.application.profile import resolve_profile

# Duck-typed fake repo (matches ADR-0004)
class FakeRepo:
    def __init__(self, profiles):
        self._profiles = profiles
    def get_by_name(self, name):
        return next((p for p in self._profiles if p.name == name), None)
    def list_enabled(self):
        return [p for p in self._profiles if p.enabled]

from campcli.domain.models import Profile
profiles = [Profile(name='test', enabled=True, max_horizon_months=3, max_drive_hours=4.0)]

try:
    result = resolve_profile(FakeRepo(profiles), None)
    print(f'Resolved: {result.name} (enabled={result.enabled})')
except Exception as e:
    print(f'ERROR: {e}')
"
```

**Expected**:
```
Resolved: test (enabled=True)
```

The use-case function is callable without Typer, without a database, with
a simple duck-typed fake — confirming the architecture follows ADR-0001
(Application depends on Protocols) and ADR-0004 (duck-typed test fakes).
