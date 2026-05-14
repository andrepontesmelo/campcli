"""Booking creation — thin orchestration over BookingRepo + park resolution."""
from datetime import date, timedelta

from .catalog import resolve_park
from .models import Booking
from .ports import BCParksApi, BookingRepo, Clock


def add(
    api: BCParksApi, *, park_query: str, start: date, nights: int,
    map_name: str | None = None, site: str | None = None,
    party_size: int | None = None, fee: float | None = None,
    notes: str | None = None,
    booking_repo: BookingRepo, clock: Clock,
) -> Booking:
    park = resolve_park(api, park_query)
    booking = Booking(
        park_id=park.park_id, park_name=park.name,
        map_name=map_name, site_name=site,
        start_date=start, end_date=start + timedelta(days=nights),
        party_size=party_size, fee=fee, notes=notes,
        created_at=clock.now(),
    )
    return booking_repo.add_booking(booking)
