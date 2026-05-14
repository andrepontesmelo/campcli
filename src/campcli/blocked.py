"""Blocklist management — thin orchestration over BlockedParkRepo + park resolution."""
from .catalog import resolve_park
from .models import BlockedPark
from .ports import BCParksApi, BlockedParkRepo, Clock


def add(
    api: BCParksApi, park_query: str, *, blocked_repo: BlockedParkRepo, clock: Clock,
) -> BlockedPark:
    park = resolve_park(api, park_query)
    bp = BlockedPark(park_id=park.park_id, park_name=park.name, added_at=clock.now())
    return blocked_repo.add_blocked(bp)


def remove(
    api: BCParksApi, park_query: str, *, blocked_repo: BlockedParkRepo,
) -> bool:
    if park_query.strip().isdigit():
        return blocked_repo.remove_blocked(int(park_query))
    park = resolve_park(api, park_query)
    return blocked_repo.remove_blocked(park.park_id)
