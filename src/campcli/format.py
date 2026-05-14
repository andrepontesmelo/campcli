"""Plain-text rendering. The only place that produces user-facing strings.

Kept intentionally minimal — one line per item, two if a URL is included.
LLM-friendly (parseable) and human-friendly (readable).
"""
from __future__ import annotations

from datetime import date

from .booking import quote_url
from .constants import nearest_holiday
from .drive_times import load_cache as load_drive_cache
from .models import AvailableSite, Booking, Map, Park, Watch, WeekendMatch


def _holiday_suffix(start: date, end: date) -> str:
    h = nearest_holiday(start, end)
    if h is None:
        return ""
    h_date, h_name = h
    return f"  🎉 {h_name} ({h_date.strftime('%a %b %d')})"


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


def render_booking(b: Booking) -> str:
    site = f" #{b.site_name}" if b.site_name else ""
    map_part = f" — {b.map_name}" if b.map_name else ""
    fee = f" ${b.fee:.2f}" if b.fee is not None else ""
    party = f" party={b.party_size}" if b.party_size is not None else ""
    notes = f"  ({b.notes})" if b.notes else ""
    return (
        f"#{b.id}  {b.park_name}{map_part}{site}  "
        f"{b.start_date.isoformat()} → {b.end_date.isoformat()}{fee}{party}{notes}"
    )


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


def _drive_hours(drive_cache: dict, pid: int) -> float | None:
    return drive_cache.get(pid, {}).get("hours")


def _drive_suffix(drive_cache: dict, pid: int) -> str:
    h = _drive_hours(drive_cache, pid)
    return f"  ({h:.1f}h)" if h is not None else ""


def _spot_label(r: WeekendMatch) -> str:
    spots = "spot" if r.available_count == 1 else "spots"
    return f"{r.available_count} {spots}"


def _match_url(r: WeekendMatch) -> str:
    return quote_url(park_id=r.park_id, map_id=r.map_id, start=r.start_date, nights=r.nights)


def _render_by_park(matches: list[WeekendMatch], drive_cache: dict, with_urls: bool) -> str:
    by_park: dict[int, list[WeekendMatch]] = {}
    for m in matches:
        by_park.setdefault(m.park_id, []).append(m)

    park_ids = sorted(
        by_park.keys(),
        key=lambda pid: (_drive_hours(drive_cache, pid) or 99.0, by_park[pid][0].park_name),
    )
    out: list[str] = []
    for pid in park_ids:
        rows = by_park[pid]
        out.append(f"{rows[0].park_name}{_drive_suffix(drive_cache, pid)}")
        by_map: dict[int, list[WeekendMatch]] = {}
        for m in rows:
            by_map.setdefault(m.map_id, []).append(m)
        for map_id in sorted(by_map.keys(), key=lambda mid: by_map[mid][0].map_name):
            map_rows = sorted(by_map[map_id], key=lambda r: (r.start_date, r.nights))
            out.append(f"  {map_rows[0].map_name}")
            for r in map_rows:
                out.append(
                    f"    {_spot_label(r)} - "
                    f"{_pretty_date(r.start_date)} -> {_pretty_date(r.end_date)} "
                    f"({r.nights}n)  {_fee_label(r.fee_per_night)}"
                    f"{_holiday_suffix(r.start_date, r.end_date)}"
                )
                if with_urls:
                    out.append(f"      {_match_url(r)}")
        out.append("")
    return "\n".join(out).rstrip()


def _render_by_weekend(matches: list[WeekendMatch], drive_cache: dict, with_urls: bool) -> str:
    by_weekend: dict[tuple, list[WeekendMatch]] = {}
    for m in matches:
        by_weekend.setdefault((m.start_date, m.nights), []).append(m)

    out: list[str] = []
    for key in sorted(by_weekend.keys()):
        start, nights = key
        end = by_weekend[key][0].end_date
        out.append(
            f"{_pretty_date(start)} -> {_pretty_date(end)} ({nights}n)"
            f"{_holiday_suffix(start, end)}"
        )

        rows = by_weekend[key]
        by_park: dict[int, list[WeekendMatch]] = {}
        for r in rows:
            by_park.setdefault(r.park_id, []).append(r)
        park_ids = sorted(
            by_park.keys(),
            key=lambda pid: (_drive_hours(drive_cache, pid) or 99.0, by_park[pid][0].park_name),
        )
        for pid in park_ids:
            prows = by_park[pid]
            out.append(f"  {prows[0].park_name}{_drive_suffix(drive_cache, pid)}")
            for r in sorted(prows, key=lambda x: x.map_name):
                out.append(
                    f"    {r.map_name} - {_spot_label(r)}  {_fee_label(r.fee_per_night)}"
                )
                if with_urls:
                    out.append(f"      {_match_url(r)}")
        out.append("")
    return "\n".join(out).rstrip()


def _weeks_label(days: int | None, suffix: str) -> str:
    if days is None:
        return f"  no booking {suffix}"
    if days == 0:
        return f"  same day as a booking ({suffix})"
    weeks = days / 7.0
    if weeks >= 1:
        return f"  {weeks:.1f} weeks {suffix}"
    return f"  {days} days {suffix}"


def render_match_message(
    m: WeekendMatch,
    *,
    prev_gap_days: int | None,
    next_gap_days: int | None,
    drive_cache: dict,
) -> str:
    drive = drive_cache.get(m.park_id, {}).get("hours")
    drive_str = f"  ({drive:.1f}h)" if drive is not None else ""
    fee = f"${m.fee_per_night:.0f}/night" if m.fee_per_night is not None else "$?/night"
    spots = "spot" if m.available_count == 1 else "spots"
    url = quote_url(park_id=m.park_id, map_id=m.map_id, start=m.start_date, nights=m.nights)
    lines = [
        f"\U0001f3d5  {m.park_name}{drive_str}",
        f"   {m.map_name}",
        f"   {m.start_date.strftime('%a %b %d')} \u2192 {m.end_date.strftime('%a %b %d')}  ({m.nights}n)  {fee}",
        f"   {m.available_count} {spots}",
    ]
    holiday = nearest_holiday(m.start_date, m.end_date)
    if holiday is not None:
        h_date, h_name = holiday
        lines.append(f"   \U0001f389 {h_name} ({h_date.strftime('%a %b %d')})")
    lines.extend([
        _weeks_label(prev_gap_days, "before nearest booking"),
        _weeks_label(next_gap_days, "after nearest booking"),
        f"   {url}",
    ])
    return "\n".join(lines)


def render_search_results(
    matches: list[WeekendMatch],
    group_by: str = "weekend",
    *,
    with_urls: bool = False,
) -> str:
    if not matches:
        return "no availability matching profile"
    drive_cache = load_drive_cache()
    if group_by == "park":
        return _render_by_park(matches, drive_cache, with_urls)
    return _render_by_weekend(matches, drive_cache, with_urls)
