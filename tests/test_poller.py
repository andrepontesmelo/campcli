from __future__ import annotations

from datetime import date

from campcli.domain.models import ParkQuery, Profile, parse_pattern
from campcli.domain.ports import TelegramUpdate
from campcli.application.poller import handle_one_command_batch
from conftest import FakeBCParksApi, FakeSearchNotifier


class TestPollerStart:
    def test_start_sends_startup_message(self, poller, fake_telegram):
        # Without any authorized users, no startup message is sent
        poller._tg_allowed_ids = [1]
        poller._settings_repo.set_setting("chat:1", "100")
        poller.start()
        assert "campcli daemon started v3" in " ".join(fake_telegram.sent)

    def test_start_registers_commands(self, poller, fake_telegram):
        poller.start()
        assert fake_telegram.commands_registered is not None


class TestPollerCommands:
    def test_verbose_on(self, poller, fake_telegram, store):
        poller._tg_allowed_ids = [1]
        fake_telegram.canned_updates = [
            TelegramUpdate(update_id=1, chat_id="100", text="/verbose on", from_id=1)
        ]
        handle_one_command_batch(poller)
        assert store.get_setting("verbose:1") == "on"
        assert "verbose logging ON" in fake_telegram.sent

    def test_verbose_off(self, poller, fake_telegram, store):
        poller._tg_allowed_ids = [1]
        store.set_setting("verbose:1", "on")
        fake_telegram.canned_updates = [
            TelegramUpdate(update_id=1, chat_id="100", text="/verbose off", from_id=1)
        ]
        handle_one_command_batch(poller)
        assert store.get_setting("verbose:1") == "off"
        assert "verbose logging OFF" in fake_telegram.sent

    def test_unknown_command(self, poller, fake_telegram, store):
        fake_telegram.canned_updates = [
            TelegramUpdate(update_id=1, chat_id="100", text="garbage", from_id=1)
        ]
        handle_one_command_batch(poller)
        assert poller._get_verbose(1) is False


class TestPollerNotificationWiring:
    def test_handle_one_command_batch_no_start_poll(self, poller, fake_notifier):
        handle_one_command_batch(poller)
        # handle_one_command_batch only processes Telegram commands;
        # run_search_once (which handles start_poll per profile) is a
        # separate step. If no profiles are enabled, start_poll is never
        # called regardless.
        assert len(fake_notifier.start_poll_calls) == 0

    def test_unauthorized_user_receives_id_message(self, poller, fake_telegram):
        poller._tg_allowed_ids = [1]
        fake_telegram.canned_updates = [
            TelegramUpdate(update_id=1, chat_id="100", text="/verbose", from_id=999)
        ]
        handle_one_command_batch(poller)
        assert "Your Telegram ID is 999" in " ".join(fake_telegram.sent)

    def test_empty_tg_allowed_ids_no_broadcast_no_commands(self, poller, fake_telegram, store):
        """When tg_allowed_ids is empty, no one is authorized, no commands processed."""
        poller._tg_allowed_ids = []
        # Even an authorized-looking user gets rejected
        fake_telegram.canned_updates = [
            TelegramUpdate(update_id=1, chat_id="100", text="/verbose on", from_id=1)
        ]
        handle_one_command_batch(poller)
        # No verbose state set
        assert store.get_setting("verbose:1") is None
        # Bot sends ID-revealing message to unauthorized user
        assert len(fake_telegram.sent) >= 1
        assert "Your Telegram ID is" in fake_telegram.sent[0]

    def test_last_seen_chat_tracking(self, poller, store, fake_telegram):
        poller._tg_allowed_ids = [1]
        fake_telegram.canned_updates = [
            TelegramUpdate(update_id=1, chat_id="200", text="/verbose on", from_id=1)
        ]
        handle_one_command_batch(poller)
        assert store.get_setting("chat:1") == "200"

    def test_unauthorized_callback_query_answered(self, poller, fake_telegram):
        """Unauthorized callback query must answer (dismiss spinner)."""
        poller._tg_allowed_ids = [1]
        fake_telegram.canned_updates = [
            TelegramUpdate(
                update_id=1, chat_id="100", text="",
                from_id=999, callback_query_id="cb_unauth",
                callback_data="verbose_on",
            )
        ]
        handle_one_command_batch(poller)
        # The unanswered callback query would leave the spinner spinning;
        # the fix requires answer_callback_query to be called.
        assert "cb_unauth" in fake_telegram.answered_callbacks


# ---------------------------------------------------------------------------
# Multi-profile Poller tests
# ---------------------------------------------------------------------------


class TestMultiProfilePoller:
    def test_empty_profiles_no_api_calls(self, poller, fake_api):
        """No enabled profiles → no API calls."""
        poller.run_search_once()
        assert len(fake_api.map_availability_calls) == 0

    def test_single_profile_calls_api(self, poller, fake_api, profile_repo):
        """Single profile with a park triggers one API call per (park, map)."""
        p = profile_repo.create(Profile(name="test", max_horizon_months=3))
        profile_repo.add_pattern("test", "fri-sun")
        profile_repo.add_park("test", "Bowron Lake")
        poller.run_search_once()
        # Bowron Lake (park_id=1) has 1 non-walk-in map (map_id=10)
        assert len(fake_api.map_availability_calls) == 1
        assert fake_api.map_availability_calls[0][:2] == (1, 10)

    def test_two_profiles_same_park_dedup(self, poller, fake_api, profile_repo):
        """Two profiles watching the same park → API called once per (park, map) pair."""
        p1 = profile_repo.create(Profile(name="p1", max_horizon_months=3))
        profile_repo.add_pattern("p1", "fri-sun")
        profile_repo.add_park("p1", "Bowron Lake")

        p2 = profile_repo.create(Profile(name="p2", max_horizon_months=3))
        profile_repo.add_pattern("p2", "fri-sun")
        profile_repo.add_park("p2", "Bowron Lake")

        poller.run_search_once()
        # One unique (park, map) pair → one API call
        assert len(fake_api.map_availability_calls) == 1
        assert fake_api.map_availability_calls[0][:2] == (1, 10)

    def test_two_profiles_different_parks(self, poller, fake_api, profile_repo):
        """Two profiles watching different parks → one API call per unique pair."""
        p1 = profile_repo.create(Profile(name="p1", max_horizon_months=3))
        profile_repo.add_pattern("p1", "fri-sun")
        profile_repo.add_park("p1", "Bowron Lake")  # park_id=1

        p2 = profile_repo.create(Profile(name="p2", max_horizon_months=3))
        profile_repo.add_pattern("p2", "fri-sun")
        profile_repo.add_park("p2", "Golden Ears")  # park_id=2

        poller.run_search_once()
        # Two unique (park, map) pairs → two API calls
        parks_called = {c[0] for c in fake_api.map_availability_calls}
        assert parks_called == {1, 2}
        assert len(fake_api.map_availability_calls) == 2

    def test_disabled_profile_skipped(self, poller, fake_api, profile_repo):
        """A disabled profile is not loaded and its park is not checked."""
        p = profile_repo.create(
            Profile(name="disabled", max_horizon_months=3, enabled=False)
        )
        profile_repo.add_pattern("disabled", "fri-sun")
        profile_repo.add_park("disabled", "Bowron Lake")

        poller.run_search_once()
        assert len(fake_api.map_availability_calls) == 0


class TestPollerFanOut:
    """Tests for per-profile tg isolation and fan-out ordering."""

    def test_per_profile_tg_isolation(self, store, clock, fake_telegram, profile_repo):
        """Each profile's notify receives only its own tg_allowed_ids chat_ids."""
        from campcli.application.drive_times import DriveTimes
        from campcli.application.poller import Poller

        # Two profiles with disjoint tg_allowed_ids, same park.
        # Note: profile_repo.create() does NOT persist tg_allowed_ids to
        # the child table — must call add_tg_id() separately.
        p100 = profile_repo.create(
            Profile(name="p100", max_horizon_months=3, tg_allowed_ids=[100])
        )
        profile_repo.add_tg_id("p100", 100)
        profile_repo.add_pattern("p100", "fri-sun")
        profile_repo.add_park("p100", "Bowron Lake")

        p200 = profile_repo.create(
            Profile(name="p200", max_horizon_months=3, tg_allowed_ids=[200])
        )
        profile_repo.add_tg_id("p200", 200)
        profile_repo.add_pattern("p200", "fri-sun")
        profile_repo.add_park("p200", "Bowron Lake")

        store.set_setting("chat:100", "chat_a")
        store.set_setting("chat:200", "chat_b")

        # Date.today() is used (not the clock fixture) — produce a matching slot.
        today = date.today()
        # Pattern "fri-sun": first Friday at or after today
        days_until_friday = (4 - today.weekday()) % 7
        first_friday = today + __import__("datetime").timedelta(days=days_until_friday)

        class RichApi(FakeBCParksApi):
            def map_availability(self, *, park_id, map_id, start, end, party_size=1):
                super().map_availability(
                    park_id=park_id, map_id=map_id, start=start, end=end,
                    party_size=party_size,
                )
                return {101: [{"availability": 0, "date": first_friday.isoformat()}]}

        api = RichApi()

        # Recording notifier — all calls land in one shared list.
        notify_records: list[tuple[str, list[str]]] = []

        class _Recorder(FakeSearchNotifier):
            def __init__(self, profile_name: str) -> None:
                super().__init__()
                self._profile_name = profile_name

            def notify(self, match, *, chat_ids=None):
                super().notify(match, chat_ids=chat_ids)
                notify_records.append(
                    (self._profile_name, list(chat_ids) if chat_ids else [])
                )

        def _factory(profile):
            return _Recorder(profile.name)

        poller = Poller(
            api=api,
            telegram=fake_telegram,
            notifier_factory=_factory,
            settings_repo=store,
            clock=clock,
            drive_times=DriveTimes.empty(),
            profile_repo=profile_repo,
            not_interested_repo=store,
        )
        poller.run_search_once()

        assert len(notify_records) == 2
        # p100 gets only chat_a
        assert ("p100", ["chat_a"]) in notify_records
        assert ("p100", ["chat_b"]) not in notify_records
        # p200 gets only chat_b
        assert ("p200", ["chat_b"]) in notify_records
        assert ("p200", ["chat_a"]) not in notify_records

    def test_fan_out_order(self, store, clock, fake_telegram, profile_repo):
        """All notifications for park A complete before any API call for park B."""
        from campcli.application.drive_times import DriveTimes
        from campcli.application.poller import Poller

        # p_a: Bowron Lake (park 1) + Golden Ears (park 2)
        # p_b: Bowron Lake (park 1) only
        # disabled: ignored
        p_a = profile_repo.create(
            Profile(name="p_a", max_horizon_months=3)
        )
        profile_repo.add_pattern("p_a", "fri-sun")
        profile_repo.add_park("p_a", "Bowron Lake")
        profile_repo.add_park("p_a", "Golden Ears")

        p_b = profile_repo.create(
            Profile(name="p_b", max_horizon_months=3)
        )
        profile_repo.add_pattern("p_b", "fri-sun")
        profile_repo.add_park("p_b", "Bowron Lake")

        profile_repo.create(
            Profile(name="c", max_horizon_months=3, enabled=False)
        )
        profile_repo.add_pattern("c", "fri-sun")
        profile_repo.add_park("c", "Bowron Lake")

        # Date.today() is used — produce a matching slot.
        today = date.today()
        days_until_friday = (4 - today.weekday()) % 7
        first_friday = today + __import__("datetime").timedelta(days=days_until_friday)

        class RichApi(FakeBCParksApi):
            def map_availability(self, *, park_id, map_id, start, end, party_size=1):
                super().map_availability(
                    park_id=park_id, map_id=map_id, start=start, end=end,
                    party_size=party_size,
                )
                return {101: [{"availability": 0, "date": first_friday.isoformat()}]}

        api = RichApi()

        # Recording notifier — records (profile_name, park_name) per notify.
        notify_order: list[tuple[str, str]] = []

        class _OrderRecorder(FakeSearchNotifier):
            def __init__(self, profile) -> None:
                super().__init__()
                self._profile = profile

            def notify(self, match, *, chat_ids=None):
                super().notify(match, chat_ids=chat_ids)
                notify_order.append((self._profile.name, match.park_name))

        def _factory(profile):
            return _OrderRecorder(profile)

        poller = Poller(
            api=api,
            telegram=fake_telegram,
            notifier_factory=_factory,
            settings_repo=store,
            clock=clock,
            drive_times=DriveTimes.empty(),
            profile_repo=profile_repo,
            not_interested_repo=store,
        )
        poller.run_search_once()

        # pair_to_profiles order: (1, 10) → [p_a, p_b], (2, 10) → [p_a]
        # Expected notify_order: p_a/Bowron, p_b/Bowron, p_a/Golden Ears
        assert len(notify_order) == 3
        assert notify_order[0] == ("p_a", "Bowron Lake")
        assert notify_order[1] == ("p_b", "Bowron Lake")
        assert notify_order[2] == ("p_a", "Golden Ears")

        # map_availability_calls: park 1 before park 2
        assert len(api.map_availability_calls) >= 2
        assert api.map_availability_calls[0][0] == 1  # Bowron Lake
        assert api.map_availability_calls[1][0] == 2  # Golden Ears
