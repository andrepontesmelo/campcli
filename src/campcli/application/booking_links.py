"""Build deep-link URLs into the BC Parks booking flow.

Format is best-effort, mirroring camply's get_reservation_link. The URL drops
the user into the search-results / pre-checkout page for the chosen park/map
and date range. Verify in a browser the first time you use it.
"""
from __future__ import annotations

from datetime import date, timedelta
from urllib.parse import urlencode

from ..constants import BASE_URL, NON_GROUP_EQUIPMENT


def quote_url(
    *,
    park_id: int,
    map_id: int,
    start: date,
    nights: int,
    party_size: int = 1,
    equipment_category_id: int = NON_GROUP_EQUIPMENT,
) -> str:
    end = start + timedelta(days=nights)
    params = {
        "resourceLocationId": park_id,
        "mapId": map_id,
        "searchTabGroupId": 0,
        "bookingCategoryId": 0,
        "startDate": start.isoformat(),
        "endDate": end.isoformat(),
        "nights": nights,
        "isReserving": "true",
        "partySize": party_size,
        "equipmentCategoryId": equipment_category_id,
        "numEquipment": 1,
    }
    return f"{BASE_URL}/create-booking/results?{urlencode(params)}"
