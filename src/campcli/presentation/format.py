"""Plain-text rendering. The only place that produces user-facing strings.

Kept intentionally minimal — one line per item, two if a URL is included.
LLM-friendly (parseable) and human-friendly (readable).
"""
from __future__ import annotations

from datetime import date, timedelta

from ..application.booking_links import quote_url
from ..domain.holidays import nearest_holiday
from ..application.drive_times import DriveTimes
from ..domain.models import AvailableSite, Booking, Map, Park, Watch, WeekendMatch


def _holiday_suffix(start: date, end: date) -> str:
    h = nearest_holiday(start, end)
    if h is None:
        return ""
    h_date, h_name = h
    return f"  🎉 {h_name} ({h_date.strftime('%a %b %d')})"


def _drive_label(park_id: int, drive_times: DriveTimes) -> str:
    h = drive_times.hours_for(park_id)
    if h is None:
        return "  —   "
    return f"{h:5.1f}h"


def render_park(p: Park, drive_times: DriveTimes | None = None) -> str:
    region = f"  [{p.region}]" if p.region else ""
    if drive_times is None:
        return f"{p.name}  (id={p.park_id}){region}"
    return f"{_drive_label(p.park_id, drive_times)}  {p.name}  (id={p.park_id}){region}"


def render_parks(parks: list[Park], drive_times: DriveTimes) -> str:
    if not parks:
        return "no parks found"
    if not drive_times:
        return "\n".join(render_park(p) for p in parks)
    # Sort closest first; parks without a drive time sink to the bottom.
    parks = sorted(
        parks,
        key=lambda p: (
            drive_times.hours_for(p.park_id) is None,
            drive_times.hours_for(p.park_id) or 0.0,
            p.name,
        ),
    )
    header = "drive  park  (drive time from Coquitlam, ferry routes counted as driving)"
    return header + "\n" + "\n".join(render_park(p, drive_times) for p in parks)


def render_park_detail(park: Park, maps: list[Map], drive_times: DriveTimes) -> str:
    lines = [render_park(park)]
    h = drive_times.hours_for(park.park_id)
    if h is not None:
        lines.append(f"  drive from Coquitlam: {h:.1f}h")
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


def _drive_suffix(drive_times: DriveTimes, pid: int) -> str:
    h = drive_times.hours_for(pid)
    return f"  ({h:.1f}h)" if h is not None else ""


def _spot_label(r: WeekendMatch) -> str:
    spots = "spot" if r.available_count == 1 else "spots"
    return f"{r.available_count} {spots}"


def _match_url(r: WeekendMatch) -> str:
    return quote_url(park_id=r.park_id, map_id=r.map_id, start=r.start_date, nights=r.nights)


def _render_by_park(matches: list[WeekendMatch], drive_times: DriveTimes, with_urls: bool) -> str:
    by_park: dict[int, list[WeekendMatch]] = {}
    for m in matches:
        by_park.setdefault(m.park_id, []).append(m)

    park_ids = sorted(
        by_park.keys(),
        key=lambda pid: (drive_times.hours_for(pid) or 99.0, by_park[pid][0].park_name),
    )
    out: list[str] = []
    for pid in park_ids:
        rows = by_park[pid]
        out.append(f"{rows[0].park_name}{_drive_suffix(drive_times, pid)}")
        by_map: dict[int, list[WeekendMatch]] = {}
        for m in rows:
            by_map.setdefault(m.map_id, []).append(m)
        for map_id in sorted(by_map.keys(), key=lambda mid: by_map[mid][0].map_name):
            map_rows = sorted(by_map[map_id], key=lambda r: (r.start_date, r.nights))
            out.append(f"  {map_rows[0].map_name}")
            for r in map_rows:
                last_night = r.end_date - timedelta(days=1)
                out.append(
                    f"    {_spot_label(r)} - "
                    f"{_pretty_date(r.start_date)} -> {_pretty_date(last_night)} "
                    f"({r.nights}n)  {_fee_label(r.fee_per_night)}"
                    f"{_holiday_suffix(r.start_date, last_night)}"
                )
                if with_urls:
                    out.append(f"      {_match_url(r)}")
        out.append("")
    return "\n".join(out).rstrip()


def _render_by_weekend(matches: list[WeekendMatch], drive_times: DriveTimes, with_urls: bool) -> str:
    by_weekend: dict[tuple, list[WeekendMatch]] = {}
    for m in matches:
        by_weekend.setdefault((m.start_date, m.nights), []).append(m)

    out: list[str] = []
    for key in sorted(by_weekend.keys()):
        start, nights = key
        last_night = by_weekend[key][0].end_date - timedelta(days=1)
        out.append(
            f"{_pretty_date(start)} -> {_pretty_date(last_night)} ({nights}n)"
            f"{_holiday_suffix(start, last_night)}"
        )

        rows = by_weekend[key]
        by_park: dict[int, list[WeekendMatch]] = {}
        for r in rows:
            by_park.setdefault(r.park_id, []).append(r)
        park_ids = sorted(
            by_park.keys(),
            key=lambda pid: (drive_times.hours_for(pid) or 99.0, by_park[pid][0].park_name),
        )
        for pid in park_ids:
            prows = by_park[pid]
            out.append(f"  {prows[0].park_name}{_drive_suffix(drive_times, pid)}")
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
    drive_times: DriveTimes,
) -> str:
    drive = drive_times.hours_for(m.park_id)
    drive_str = f"  ({drive:.1f}h)" if drive is not None else ""
    fee = f"${m.fee_per_night:.0f}/night" if m.fee_per_night is not None else "$?/night"
    spots = "spot" if m.available_count == 1 else "spots"
    url = quote_url(park_id=m.park_id, map_id=m.map_id, start=m.start_date, nights=m.nights)
    lines = [
        f"\U0001f3d5  {m.park_name}{drive_str}",
        f"   {m.map_name}",
        f"   {m.start_date.strftime('%a %b %d')} \u2192 {(m.end_date - timedelta(days=1)).strftime('%a %b %d')}  ({m.nights}n)  {fee}",
        f"   {m.available_count} {spots}",
    ]
    holiday = nearest_holiday(m.start_date, m.end_date - timedelta(days=1))
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
    drive_times: DriveTimes,
) -> str:
    if not matches:
        return "no availability matching profile"
    if group_by == "park":
        return _render_by_park(matches, drive_times, with_urls)
    return _render_by_weekend(matches, drive_times, with_urls)
