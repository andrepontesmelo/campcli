"""Test availability filtering fan-out — proves BCParksApi seam pays off."""
from datetime import date

from campcli.availability import check_map, check_park
from campcli.constants import AVAILABILITY_AVAILABLE, AVAILABILITY_RESERVED
from campcli.models import AvailableSite, Map, Park


class TestCheckMap:
    def test_available_sites_filtered_by_slot_availability(self):
        """Only sites where EVERY slot is AVAILABLE pass through _is_available."""
        park = Park(park_id=1, name="Test Park")
        m = Map(map_id=10, park_id=1, name="Loop A")

        class FakeApi:
            def map_availability(self, *, park_id, map_id, start, end, party_size=1):
                return {
                    101: [{"availability": AVAILABILITY_AVAILABLE, "resourceName": "A"}],
                    102: [{"availability": AVAILABILITY_RESERVED}],
                    103: [{"availability": AVAILABILITY_AVAILABLE}, {"availability": AVAILABILITY_AVAILABLE}],
                    104: [{"availability": AVAILABILITY_AVAILABLE}, {"availability": AVAILABILITY_RESERVED}],
                }
            def list_parks(self, *, refresh=False):
                return [park]
            def list_maps(self, park_id):
                return [m]
            def resource_details(self, *, park_id, map_id):
                return {}

        result = check_map(FakeApi(), park, m, date(2026, 7, 1), 2, 1)

        assert len(result) == 2
        assert AvailableSite(
            park_id=1, park_name="Test Park", map_id=10, map_name="Loop A",
            site_id=101, site_name="A", start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 3),
        ) in result
        assert AvailableSite(
            park_id=1, park_name="Test Park", map_id=10, map_name="Loop A",
            site_id=103, site_name=None, start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 3),
        ) in result


class TestCheckPark:
    def test_fans_out_across_multiple_maps(self):
        """check_park calls api.list_maps then check_map per map."""
        park = Park(park_id=2, name="Multi Map Park")

        class FakeApi:
            def list_maps(self, park_id):
                return [
                    Map(map_id=20, park_id=2, name="Loop A"),
                    Map(map_id=21, park_id=2, name="Loop B"),
                ]
            def map_availability(self, *, park_id, map_id, start, end, party_size=1):
                return {map_id: [{"availability": AVAILABILITY_AVAILABLE}]}
            def list_parks(self, *, refresh=False):
                return [park]
            def resource_details(self, *, park_id, map_id):
                return {}

        result = check_park(FakeApi(), park, date(2026, 8, 1), 1, 1)

        assert len(result) == 2
        names = {r.map_name for r in result}
        assert names == {"Loop A", "Loop B"}
