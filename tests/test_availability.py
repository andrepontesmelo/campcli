"""Test availability filtering fan-out — proves BCParksApi seam pays off."""
from datetime import date

from campcli.application.availability import check_map, check_map_from_data, check_park
from campcli.domain.models import AvailableSite, Map, Park
from campcli.domain.goingtocamp_codes import AVAILABILITY_AVAILABLE, AVAILABILITY_RESERVED


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


class TestCheckMapFromData:
    """Bulk-fetch daily grid is positional and date-less: slot i == night fetch_start+i."""

    park = Park(park_id=1, name="Test Park")
    m = Map(map_id=10, park_id=1, name="Loop A")

    def _grid(self, codes: list[int]) -> dict[int, list[dict]]:
        return {101: [{"availability": c} for c in codes]}

    def test_window_all_nights_free_matches(self):
        # fetch_start day0; nights at idx 2,3 free, others reserved
        resources = self._grid([1, 1, 0, 0, 1])
        fetch_start = date(2026, 9, 21)
        out = check_map_from_data(
            self.park, self.m, date(2026, 9, 23), 2, resources, fetch_start=fetch_start
        )
        assert len(out) == 1
        assert out[0].start_date == date(2026, 9, 23)
        assert out[0].end_date == date(2026, 9, 25)

    def test_window_spanning_reserved_night_rejected(self):
        # idx1 reserved -> window [idx0, idx1) fails
        resources = self._grid([0, 1, 0, 0])
        out = check_map_from_data(
            self.park, self.m, date(2026, 9, 21), 2, resources, fetch_start=date(2026, 9, 21)
        )
        assert out == []

    def test_window_truncated_past_grid_end_rejected(self):
        # only 2 nights of data but a 2-night window starting at the last night
        resources = self._grid([0, 0])
        out = check_map_from_data(
            self.park, self.m, date(2026, 9, 22), 2, resources, fetch_start=date(2026, 9, 21)
        )
        assert out == []

    def test_offset_before_fetch_start_rejected(self):
        resources = self._grid([0, 0, 0])
        out = check_map_from_data(
            self.park, self.m, date(2026, 9, 20), 2, resources, fetch_start=date(2026, 9, 21)
        )
        assert out == []
