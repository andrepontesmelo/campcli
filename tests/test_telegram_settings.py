"""Unit tests for telegram_settings module-level functions."""
from __future__ import annotations

from campcli.application.telegram_settings import (
    get_chat_id,
    get_verbose,
    refresh_tg_allowed_ids,
    set_chat_id,
    set_verbose,
)
from campcli.domain.models import Profile


class FakeSettingsRepo:
    """Duck-typed fake SettingsRepo — no mock framework needed."""

    def __init__(self) -> None:
        self._data: dict[str, str] = {}

    def get_setting(self, key: str) -> str | None:
        return self._data.get(key)

    def set_setting(self, key: str, value: str) -> None:
        self._data[key] = value


class FakeProfileRepo:
    """Duck-typed fake ProfileRepo for refresh_tg_allowed_ids tests."""

    def __init__(self, enabled_profiles: list[Profile] | None = None) -> None:
        self._enabled = enabled_profiles or []

    def list_enabled(self) -> list[Profile]:
        return list(self._enabled)


class TestGetVerbose:
    def test_default_is_false(self):
        repo = FakeSettingsRepo()
        assert get_verbose(repo, 1) is False

    def test_on_returns_true(self):
        repo = FakeSettingsRepo()
        repo.set_setting("verbose:1", "on")
        assert get_verbose(repo, 1) is True

    def test_off_returns_false(self):
        repo = FakeSettingsRepo()
        repo.set_setting("verbose:1", "off")
        assert get_verbose(repo, 1) is False

    def test_different_users_isolated(self):
        repo = FakeSettingsRepo()
        repo.set_setting("verbose:1", "on")
        assert get_verbose(repo, 1) is True
        assert get_verbose(repo, 2) is False


class TestSetVerbose:
    def test_set_on(self):
        repo = FakeSettingsRepo()
        set_verbose(repo, 1, True)
        assert repo.get_setting("verbose:1") == "on"

    def test_set_off(self):
        repo = FakeSettingsRepo()
        repo.set_setting("verbose:1", "on")
        set_verbose(repo, 1, False)
        assert repo.get_setting("verbose:1") == "off"

    def test_toggle(self):
        repo = FakeSettingsRepo()
        set_verbose(repo, 1, True)
        assert repo.get_setting("verbose:1") == "on"
        set_verbose(repo, 1, False)
        assert repo.get_setting("verbose:1") == "off"
        set_verbose(repo, 1, True)
        assert repo.get_setting("verbose:1") == "on"


class TestGetChatId:
    def test_default_is_none(self):
        repo = FakeSettingsRepo()
        assert get_chat_id(repo, 1) is None

    def test_returns_stored_chat(self):
        repo = FakeSettingsRepo()
        repo.set_setting("chat:1", "100")
        assert get_chat_id(repo, 1) == "100"

    def test_different_users_isolated(self):
        repo = FakeSettingsRepo()
        repo.set_setting("chat:1", "100")
        assert get_chat_id(repo, 1) == "100"
        assert get_chat_id(repo, 2) is None


class TestSetChatId:
    def test_set_and_read_back(self):
        repo = FakeSettingsRepo()
        set_chat_id(repo, 42, "chat_42")
        assert repo.get_setting("chat:42") == "chat_42"

    def test_overwrite(self):
        repo = FakeSettingsRepo()
        repo.set_setting("chat:1", "old")
        set_chat_id(repo, 1, "new")
        assert repo.get_setting("chat:1") == "new"


class TestRefreshTgAllowedIds:
    def test_empty_profiles_returns_empty(self):
        profile_repo = FakeProfileRepo([])
        assert refresh_tg_allowed_ids(profile_repo) == []

    def test_no_enabled_profiles_returns_empty(self):
        p = Profile(name="test", enabled=False)
        profile_repo = FakeProfileRepo(enabled_profiles=[])
        assert refresh_tg_allowed_ids(profile_repo) == []

    def test_single_profile_returns_ids(self):
        p = Profile(name="test", enabled=True, tg_allowed_ids=[100, 200])
        profile_repo = FakeProfileRepo(enabled_profiles=[p])
        assert refresh_tg_allowed_ids(profile_repo) == [100, 200]

    def test_union_across_profiles(self):
        p1 = Profile(name="a", enabled=True, tg_allowed_ids=[100, 200])
        p2 = Profile(name="b", enabled=True, tg_allowed_ids=[200, 300])
        profile_repo = FakeProfileRepo(enabled_profiles=[p1, p2])
        assert refresh_tg_allowed_ids(profile_repo) == [100, 200, 300]

    def test_sorted_return(self):
        p1 = Profile(name="a", enabled=True, tg_allowed_ids=[3, 1, 2])
        profile_repo = FakeProfileRepo(enabled_profiles=[p1])
        assert refresh_tg_allowed_ids(profile_repo) == [1, 2, 3]

    def test_disabled_profiles_not_included(self):
        enabled = Profile(name="on", enabled=True, tg_allowed_ids=[10])
        disabled = Profile(name="off", enabled=False, tg_allowed_ids=[20])
        profile_repo = FakeProfileRepo(enabled_profiles=[enabled])
        assert refresh_tg_allowed_ids(profile_repo) == [10]
