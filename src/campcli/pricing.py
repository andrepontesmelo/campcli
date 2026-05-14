"""Per-night fee estimation.

The /api/availability/map endpoint returns no pricing. Probing common pricing
paths (/api/resource/details, /api/fees, /api/feeStructure, etc.) all return
404 against the live BC Parks GoingToCamp API — the live endpoint shape we
expected from the brief wasn't there. Until we identify the real endpoint
(may require capturing booking-flow XHRs in the browser), fall back to a
seasonal estimate based on BC Parks' published 2026 rates.

Numbers come from the user's research:
  shoulder/off-season:  ~$31/night (avg, BC resident, frontcountry)
  peak (Jun 15 - Labour Day):  ~$43/night
"""
from __future__ import annotations

from datetime import date

from .constants import PEAK_START_MONTH_DAY


SHOULDER_FEE = 31.0
PEAK_FEE = 43.0


def labour_day(year: int) -> date:
    """First Monday of September."""
    d = date(year, 9, 1)
    return d.replace(day=1 + ((7 - d.weekday()) % 7))


def season_for(d: date) -> str:
    peak_start = date(d.year, *PEAK_START_MONTH_DAY)
    peak_end = labour_day(d.year)
    return "peak" if peak_start <= d <= peak_end else "shoulder"


def fee_per_night(on_date: date) -> float:
    """Return estimated per-night base fee for a campsite on `on_date`.

    A pure seasonal estimate — no live data. See ADR-0008 for why this is
    not yet a FeeSource port.
    """
    return PEAK_FEE if season_for(on_date) == "peak" else SHOULDER_FEE
