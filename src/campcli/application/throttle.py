"""Request-interval throttle setting — read with sane default fallback."""
from __future__ import annotations

from ..domain.ports import SettingsRepo

DEFAULT_REQUEST_INTERVAL_SECS = 5.0
SETTING_REQUEST_INTERVAL_KEY = "request_interval_secs"


def read_request_interval(repo: SettingsRepo) -> float:
    raw = repo.get_setting(SETTING_REQUEST_INTERVAL_KEY)
    if raw is None:
        return DEFAULT_REQUEST_INTERVAL_SECS
    try:
        return float(raw)
    except (ValueError, TypeError):
        return DEFAULT_REQUEST_INTERVAL_SECS
