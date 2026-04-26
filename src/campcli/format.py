"""Plain-text rendering. The only place that produces user-facing strings.

Kept intentionally minimal — one line per item, two if a URL is included.
LLM-friendly (parseable) and human-friendly (readable).
"""
from __future__ import annotations

from .booking import quote_url
from .drive_times import load_cache as load_drive_cache
from .models import AvailableSite, Map, Park, Watch, WeekendMatch


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


def _fee_label(fee: float | None) -> str:
    return f"${fee:.0f}/night" if fee is not None else "$?/night"


def _pretty_date(d) -> str:
    return d.strftime("%a, %b %d")


def render_search_results(matches: list[WeekendMatch]) -> str:
    if not matches:
        return "no availability matching profile"
    drive_cache = load_drive_cache()

    def park_drive(pid: int) -> float:
        h = drive_cache.get(pid, {}).get("hours")
        return h if h is not None else 99.0

    by_park: dict[int, list[WeekendMatch]] = {}
    for m in matches:
        by_park.setdefault(m.park_id, []).append(m)

    park_ids = sorted(by_park.keys(), key=lambda pid: (park_drive(pid), by_park[pid][0].park_name))
    out: list[str] = []
    for pid in park_ids:
        rows = by_park[pid]
        park_name = rows[0].park_name
        h = drive_cache.get(pid, {}).get("hours")
        drive = f"  ({h:.1f}h)" if h is not None else ""
        out.append(f"{park_name}{drive}")

        by_map: dict[int, list[WeekendMatch]] = {}
        for m in rows:
            by_map.setdefault(m.map_id, []).append(m)
        for map_id in sorted(by_map.keys(), key=lambda mid: by_map[mid][0].map_name):
            map_rows = sorted(by_map[map_id], key=lambda r: (r.start_date, r.nights))
            out.append(f"  {map_rows[0].map_name}")
            for r in map_rows:
                spots = "spot" if r.available_count == 1 else "spots"
                out.append(
                    f"    {r.available_count} {spots} - "
                    f"{_pretty_date(r.start_date)} -> {_pretty_date(r.end_date)} "
                    f"({r.nights}n)  {_fee_label(r.fee_per_night)}"
                )
        out.append("")
    return "\n".join(out).rstrip()
