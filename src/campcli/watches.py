"""Watch service: thin orchestration over WatchRepo + availability."""
from __future__ import annotations

from datetime import date

from .availability import check_park
from .catalog import find_park
from .models import AvailableSite, Park, Watch
from .ports import BCParksApi, Clock, WatchRepo


def add(
    park_id: int, start: date, nights: int, party_size: int = 1,
    label: str | None = None, *, watch_repo: WatchRepo, clock: Clock,
) -> Watch:
    w = Watch(
        park_id=park_id, start_date=start, nights=nights,
        party_size=party_size, label=label, created_at=clock.now(),
    )
    return watch_repo.add_watch(w)


def list_all(*, watch_repo: WatchRepo) -> list[Watch]:
    return watch_repo.list_watches()


def remove(watch_id: int, *, watch_repo: WatchRepo) -> bool:
    return watch_repo.remove_watch(watch_id)


def run_one(api: BCParksApi, watch: Watch, parks: list[Park]) -> tuple[Watch, list[AvailableSite]]:
    park = find_park(parks, watch.park_id)
    if park is None:
        park = Park(park_id=watch.park_id, name=f"park {watch.park_id}")
    sites = check_park(api, park, watch.start_date, watch.nights, watch.party_size)
    return watch, sites


def run_all(
    api: BCParksApi, *, watch_repo: WatchRepo, watch_id: int | None = None,
) -> list[tuple[Watch, list[AvailableSite]]]:
    watches = watch_repo.list_watches()
    if watch_id is not None:
        watches = [w for w in watches if w.id == watch_id]
    parks = api.list_parks()
    return [run_one(api, w, parks) for w in watches]
