"""Offscreen tests for the redesigned profile cards."""

from __future__ import annotations

from types import SimpleNamespace

from PySide6.QtCore import QObject, Qt, Signal

from mihomo_lite.models.app_state import ConnectionState
from mihomo_lite.models.profile import Profile, ProfileKind
from mihomo_lite.ui.profile_page import ProfilePage


class FakeProfiles(QObject):
    profiles_changed = Signal()
    active_changed = Signal(object)

    def __init__(self, profiles: list[Profile], active_id: str) -> None:
        super().__init__()
        self._profiles = profiles
        self._active = active_id

    @property
    def profiles(self) -> list[Profile]:
        return list(self._profiles)

    @property
    def active_id(self) -> str:
        return self._active

    def get(self, profile_id: str) -> Profile | None:
        return next((p for p in self._profiles if p.id == profile_id), None)

    def profile_path(self, profile_id: str):
        from pathlib import Path

        return Path("missing") / profile_id / "original.yaml"

    def set_active(self, profile_id: str) -> None:
        self._active = profile_id
        self.active_changed.emit(self.get(profile_id))


class FakeUpdates(QObject):
    started = Signal()
    finished = Signal(int, int)
    profile_failed = Signal(str, str)
    active_profile_updated = Signal(object)

    def update_all(self, force: bool = False) -> bool:
        return True


class FakeConnection(QObject):
    state_changed = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.state = ConnectionState.STOPPED

    @property
    def is_connected(self) -> bool:
        return False


def _page(qtbot) -> tuple[ProfilePage, FakeProfiles]:
    first = Profile(
        id="p1",
        name="First subscription",
        kind=ProfileKind.SUBSCRIPTION,
        url="https://example.com/sub",
        proxy_count=12,
        group_count=3,
        rule_count=40,
    )
    second = Profile(
        id="p2",
        name="Second subscription",
        kind=ProfileKind.LOCAL,
        proxy_count=7,
        group_count=2,
        rule_count=30,
    )
    profiles = FakeProfiles([first, second], "p2")
    services = SimpleNamespace(
        profiles=profiles,
        updates=FakeUpdates(),
        connection=FakeConnection(),
        settings=SimpleNamespace(),
        runner=SimpleNamespace(),
    )
    page = ProfilePage(services)
    qtbot.addWidget(page)
    page.show()
    qtbot.wait(20)
    return page, profiles


def test_profile_page_renders_one_card_per_profile(qtbot):
    page, _profiles = _page(qtbot)
    assert set(page._cards) == {"p1", "p2"}
    assert page._cards["p2"].property("active") == "true"
    assert page._cards["p2"].property("selected") == "true"


def test_rule_check_result_is_cached(qtbot, monkeypatch):
    page, _profiles = _page(qtbot)
    profile = page._services.profiles.get("p1")
    assert profile is not None
    calls: list[str] = []
    original = page._describe_rules

    def counted(item):
        calls.append(item.id)
        return original(item)

    monkeypatch.setattr(page, "_describe_rules", counted)
    page._refresh_rule_hint(profile)
    page._refresh_rule_hint(profile)
    assert calls == ["p1"]


def test_clicking_a_profile_card_selects_it(qtbot):
    page, _profiles = _page(qtbot)
    card = page._cards["p1"]
    qtbot.mouseClick(card, Qt.MouseButton.LeftButton)
    assert page._selected_id == "p1"
    assert card.property("selected") == "true"
    assert page._cards["p2"].property("selected") == "false"
