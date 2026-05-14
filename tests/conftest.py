from datetime import date

import pytest

from campcli.models import Map, Park
from campcli.ports import BCParksApi


class FakeBCParksApi(BCParksApi):
    def __init__(self, parks: list[Park] | None = None):
        self._parks = parks or [
            Park(park_id=1, name="Bowron Lake", region="Cariboo"),
            Park(park_id=2, name="Golden Ears", region="Lower Mainland"),
        ]

    def list_parks(self, *, refresh: bool = False) -> list[Park]:
        return self._parks

    def list_maps(self, park_id: int) -> list[Map]:
        return [Map(map_id=10, park_id=park_id, name="Main")]

    def map_availability(
        self, *, park_id: int, map_id: int, start: date, end: date, party_size: int = 1
    ) -> dict:
        return {}

    def resource_details(self, *, park_id: int, map_id: int) -> dict:
        return {}


@pytest.fixture
def fake_api():
    return FakeBCParksApi()


@pytest.fixture
def tmp_db(monkeypatch, tmp_path):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr("campcli.store.CONFIG_DIR", tmp_path)
    monkeypatch.setattr("campcli.store.DB_PATH", db_path)
    return db_path
