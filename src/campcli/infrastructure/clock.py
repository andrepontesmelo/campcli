"""SystemClock — trivial Infrastructure adapter for the Clock port."""
from __future__ import annotations

from datetime import datetime


class SystemClock:
    def now(self) -> datetime:
        return datetime.now()
