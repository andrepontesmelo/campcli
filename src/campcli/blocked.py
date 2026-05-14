from .catalog import resolve_park
from .models import BlockedPark
from .ports import BCParksApi
from . import store


def add(api: BCParksApi, park_query: str) -> BlockedPark:
    park = resolve_park(api, park_query)
    return store.add_blocked_park(park.park_id, park.name)


def remove(api: BCParksApi, park_query: str) -> bool:
    if park_query.strip().isdigit():
        return store.remove_blocked_park(int(park_query))
    park = resolve_park(api, park_query)
    return store.remove_blocked_park(park.park_id)
