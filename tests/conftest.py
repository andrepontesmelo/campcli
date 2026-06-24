from datetime import date, datetime

import pytest

from campcli.domain.models import Map, Park
from campcli.domain.ports import BCParksApi, Telegram, TelegramUpdate


class FakeBCParksApi:
    def __init__(self, parks: list[Park] | None = None):
        self._parks = parks or [
            Park(park_id=1, name="Bowron Lake", region="Cariboo"),
            Park(park_id=2, name="Golden Ears", region="Lower Mainland"),
        ]
        self.map_availability_calls: list[tuple[int, int, date, date]] = []

    def list_parks(self, *, refresh: bool = False) -> list[Park]:
        return self._parks

    def list_maps(self, park_id: int) -> list[Map]:
        return [Map(map_id=10, park_id=park_id, name="Main")]

    def map_availability(
        self, *, park_id: int, map_id: int, start: date, end: date, party_size: int = 1
    ) -> dict:
        self.map_availability_calls.append((park_id, map_id, start, end))
        return {}

    def resource_details(self, *, park_id: int, map_id: int) -> dict:
        return {}


class FakeTelegram:
    def __init__(self):
        self.sent: list[str] = []
        self.canned_updates: list[TelegramUpdate] = []
        self.commands_registered: list | None = None
        self.inline_keyboards_sent: list[tuple[str, str, list]] = []
        self.edited_messages: list[tuple[str, int, str | None, list | None]] = []
        self.answered_callbacks: list[str] = []

    def send_to(self, chat_id: str, text: str) -> None:
        self.sent.append(text)

    def poll_updates(self, offset: int | None = None, long_poll_timeout: int = 0) -> list[TelegramUpdate]:
        out, self.canned_updates = self.canned_updates, []
        return out

    def set_my_commands(self, commands: list) -> None:
        self.commands_registered = commands

    def send_inline_keyboard(
        self, chat_id: str, text: str, buttons: list[list[dict[str, str]]]
    ) -> int:
        self.inline_keyboards_sent.append((chat_id, text, buttons))
        return 42  # fake message_id

    def edit_message_reply_markup(
        self,
        chat_id: str,
        message_id: int,
        text: str | None = None,
        buttons: list[list[dict[str, str]]] | None = None,
    ) -> None:
        self.edited_messages.append((chat_id, message_id, text, buttons))

    def answer_callback_query(self, query_id: str, text: str | None = None) -> None:
        self.answered_callbacks.append(query_id)


class FakeSearchNotifier:
    def __init__(self):
        self.start_poll_calls: list[tuple[list, set[int]]] = []
        self.notify_calls: list = []

    def start_poll(self, booking_starts, blocked_park_ids):
        self.start_poll_calls.append((booking_starts, blocked_park_ids))

    def notify(self, match, *, chat_ids=None):
        self.notify_calls.append(match)

    def set_log(self, _log):
        pass


class FrozenClock:
    def __init__(self, value: datetime) -> None:
        self._value = value

    def now(self) -> datetime:
        return self._value


# Static assertions: fakes satisfy their Protocols.
_bcparks_api: BCParksApi = FakeBCParksApi()
_telegram: Telegram = FakeTelegram()


@pytest.fixture
def fake_api():
    return FakeBCParksApi()


@pytest.fixture
def fake_telegram():
    return FakeTelegram()


@pytest.fixture
def store(tmp_path):
    from campcli.infrastructure.store import SqliteStore
    return SqliteStore(tmp_path / "test.db")


@pytest.fixture
def profile_repo(tmp_path, clock):
    from campcli.infrastructure.store import SqliteStore
    return SqliteStore(tmp_path / "profile_test.db", clock=clock)


@pytest.fixture
def clock():
    return FrozenClock(datetime(2026, 1, 1, 12, 0, 0))


@pytest.fixture
def fake_notifier():
    return FakeSearchNotifier()


@pytest.fixture
def notifier_factory():
    """Return a factory that creates FakeSearchNotifier instances."""

    def _factory(_profile):
        return FakeSearchNotifier()

    return _factory


@pytest.fixture
def poller(store, clock, fake_api, fake_telegram, notifier_factory, profile_repo):
    from campcli.application.drive_times import DriveTimes
    from campcli.application.poller import Poller
    return Poller(
        api=fake_api, telegram=fake_telegram,
        notifier_factory=notifier_factory,
        settings_repo=store, clock=clock,
        drive_times=DriveTimes.empty(),
        profile_repo=profile_repo,
    )
