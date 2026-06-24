"""Profile — legacy module (kept as import-shim for backward compat).

All domain types have moved to ``domain/models.py``.
The old JSON-based ``Profile`` model and ``load_profile`` are removed.
This file will be deleted in a future cleanup pass.
"""

# Re-exports for any remaining imports.
from ..domain.models import PatternSpec, parse_pattern  # noqa: F401
