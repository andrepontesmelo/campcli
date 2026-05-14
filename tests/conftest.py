from datetime import date

import pytest

from campcli.models import Map, Park
from campcli.ports import BCParksApi, Telegram, TelegramUpdate


class FakeBCParksApi:
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


class FakeTelegram:
    def __init__(self):
        self.sent: list[str] = []
        self.canned_updates: list[TelegramUpdate] = []

    def send(self, text: str) -> None:
        self.sent.append(text)

    def poll_updates(self, offset: int | None = None) -> list[TelegramUpdate]:
        out, self.canned_updates = self.canned_updates, []
        return out


# Static assertions: fakes satisfy their Protocols.
_: BCParksApi = FakeBCParksApi()
_: Telegram = FakeTelegram()


@pytest.fixture
def fake_api():
    return FakeBCParksApi()


@pytest.fixture
def fake_telegram():
    return FakeTelegram()


@pytest.fixture
def tmp_db(monkeypatch, tmp_path):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr("campcli.store.CONFIG_DIR", tmp_path)
    monkeypatch.setattr("campcli.store.DB_PATH", db_path)
    return db_path


@pytest.fixture
def poller(tmp_db, fake_api, fake_telegram):
    from campcli.poller import Poller
    return Poller(api=fake_api, telegram=fake_telegram)
