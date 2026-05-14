"""Park and map lookup utilities — pure Application code.

Fetching and caching live in the adapter (api.py). This module only contains
lookup logic that operates on already-resolved Domain objects.
"""
from __future__ import annotations

from .models import Park
from .ports import BCParksApi


def find_park(parks: list[Park], park_id: int) -> Park | None:
    return next((p for p in parks if p.park_id == park_id), None)


def resolve_park(api: BCParksApi, query: str) -> Park:
    """Resolve a free-text park name to a Park.

    Tries exact (case-insensitive) match first, then substring. Raises
    ValueError on no match or ambiguous match (with candidate names).
    """
    parks = api.list_parks()
    q = query.strip().lower()
    exact = [p for p in parks if p.name.lower() == q]
    if len(exact) == 1:
        return exact[0]
    matches = [p for p in parks if q in p.name.lower()]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise ValueError(f"no park matches {query!r}")
    names = ", ".join(p.name for p in matches[:5])
    more = "" if len(matches) <= 5 else f" (+{len(matches) - 5} more)"
    raise ValueError(f"ambiguous park {query!r}: matches {names}{more} — be more specific")
