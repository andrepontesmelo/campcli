"""Plain-text rendering. The only place that produces user-facing strings.

Kept intentionally minimal — one line per item, two if a URL is included.
LLM-friendly (parseable) and human-friendly (readable).
"""
from __future__ import annotations

from .booking import quote_url
from .drive_times import load_cache as load_drive_cache
from .models import AvailableSite, Map, Park, Watch


def _drive_label(park_id: int, drive_cache: dict) -> str:
    entry = drive_cache.get(park_id)
    if not entry or entry.get("hours") is None:
        return "  —   "
    return f"{entry['hours']:5.1f}h"


def render_park(p: Park, drive_cache: dict | None = None) -> str:
    region = f"  [{p.region}]" if p.region else ""
    if drive_cache is None:
        return f"{p.name}  (id={p.park_id}){region}"
    return f"{_drive_label(p.park_id, drive_cache)}  {p.name}  (id={p.park_id}){region}"


def render_parks(parks: list[Park]) -> str:
    if not parks:
        return "no parks found"
    drive_cache = load_drive_cache()
    if not drive_cache:
        return "\n".join(render_park(p) for p in parks)
    # Sort closest first; parks without a drive time sink to the bottom.
    parks = sorted(
        parks,
        key=lambda p: (
            drive_cache.get(p.park_id, {}).get("hours") is None,
            drive_cache.get(p.park_id, {}).get("hours") or 0.0,
            p.name,
        ),
    )
    header = "drive  park  (drive time from Coquitlam, ferry routes counted as driving)"
    return header + "\n" + "\n".join(render_park(p, drive_cache) for p in parks)


def render_park_detail(park: Park, maps: list[Map]) -> str:
    drive_cache = load_drive_cache()
    lines = [render_park(park)]
    entry = drive_cache.get(park.park_id)
    if entry and entry.get("hours") is not None:
        lines.append(f"  drive from Coquitlam: {entry['hours']:.1f}h")
    lines.append(f"  {len(maps)} maps:")
    for m in maps:
        lines.append(f"    - {m.name}  (map_id={m.map_id})")
    return "\n".join(lines)


def render_watch(w: Watch) -> str:
    label = f' "{w.label}"' if w.label else ""
    return (
        f"#{w.id}{label}  park={w.park_id}  "
        f"{w.start_date.isoformat()} +{w.nights}n  party={w.party_size}"
    )


def render_watches(watches: list[Watch]) -> str:
    if not watches:
        return "no watches"
    return "\n".join(render_watch(w) for w in watches)


def render_available(s: AvailableSite, *, with_url: bool = True) -> str:
    nights = (s.end_date - s.start_date).days
    site_label = f"site #{s.site_name or s.site_id}"
    line = (
        f"{s.park_name} - {s.map_name} - {site_label} - "
        f"{s.start_date.isoformat()} -> {s.end_date.isoformat()} ({nights}n)"
    )
    if not with_url:
        return line
    url = quote_url(park_id=s.park_id, map_id=s.map_id, start=s.start_date, nights=nights)
    return f"{line}\n  {url}"


def render_available_list(sites: list[AvailableSite]) -> str:
    if not sites:
        return "no availability"
    return "\n".join(render_available(s) for s in sites)
