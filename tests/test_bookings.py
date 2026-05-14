from datetime import date

from campcli import bookings, store


class TestBookingsAdd:
    def test_add_booking_creates_store_entry(self, fake_api, tmp_db):
        b = bookings.add(fake_api, park_query="bowron", start=date(2026, 8, 15), nights=2)
        rows = store.list_bookings()
        assert len(rows) == 1
        row = rows[0]
        assert row.park_name == "Bowron Lake"
        assert row.start_date == date(2026, 8, 15)
        assert row.end_date == date(2026, 8, 17)
        assert row.park_id == 1
        assert row.id is not None

    def test_add_booking_all_optional_fields(self, fake_api, tmp_db):
        b = bookings.add(
            fake_api, park_query="bowron", start=date(2026, 7, 1), nights=3,
            map_name="Loop A", site="B12", party_size=4, fee=30.0, notes="test",
        )
        assert b.map_name == "Loop A"
        assert b.site_name == "B12"
        assert b.party_size == 4
        assert b.fee == 30.0
        assert b.notes == "test"
