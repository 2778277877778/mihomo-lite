"""Offscreen tests for the proxy history and batch-test UI."""

from __future__ import annotations

from types import SimpleNamespace

from PySide6.QtCore import QObject, Signal

from mihomo_lite.models.app_state import AppSettings, ConnectionState
from mihomo_lite.models.proxy import ProxyGroup, ProxyNode
from mihomo_lite.ui.proxy_page import ProxyPage


class FakeProxy(QObject):
    groups_updated = Signal(object, object)
    delays_updated = Signal(object)
    selection_changed = Signal(str, str)
    failed = Signal(str)
    node_stats = Signal(object)
    mode_changed = Signal(str)
    batch_delay_started = Signal(int)
    batch_delay_progress = Signal(int, int)
    batch_delay_finished = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.batch_running = False
        self.nodes: dict[str, ProxyNode] = {}
        self.selected: list[tuple[str, str]] = []

    def refresh(self) -> None:
        pass

    def select(self, group: str, node: str) -> None:
        self.selected.append((group, node))


class FakeConnection(QObject):
    state_changed = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.state = ConnectionState.CONNECTED

    @property
    def is_connected(self) -> bool:
        return True

    @property
    def session(self) -> object:
        return SimpleNamespace(proxy_server="127.0.0.1:1")


class FakeSettings:
    def __init__(self) -> None:
        self.current = AppSettings()
        self.updates: list[dict] = []

    def update(self, **changes: object) -> AppSettings:
        self.updates.append(dict(changes))
        data = self.current.model_dump()
        data.update(changes)
        self.current = AppSettings.model_validate(data)
        return self.current


class FakeProfiles:
    def active_profile(self) -> object:
        return None


def _page(qtbot):
    proxy = FakeProxy()
    settings = FakeSettings()
    services = SimpleNamespace(
        proxy=proxy,
        connection=FakeConnection(),
        settings=settings,
        profiles=FakeProfiles(),
        runner=None,
    )
    page = ProxyPage(services)
    qtbot.addWidget(page)
    page.show()
    qtbot.wait(20)
    group = ProxyGroup(
        name="G", type="Selector", now="node-a", members=["node-a", "node-b", "DIRECT"]
    )
    group.delays.update({"node-a": 100, "node-b": 200})
    nodes = {"node-a": ProxyNode("node-a"), "node-b": ProxyNode("node-b")}
    page._on_groups([group], nodes)
    return page, proxy, settings, group


def test_previous_node_button_switches_back(qtbot):
    page, proxy, settings, group = _page(qtbot)
    page._apply_item(page._node_list.item(1))
    assert proxy.selected[-1] == ("G", "node-b")
    assert settings.current.last_proxy_nodes == {"G": "node-a"}
    assert page._previous_button.isEnabled()

    page._use_previous_node()
    assert proxy.selected[-1] == ("G", "node-a")
    assert group.now == "node-a"
    assert settings.current.last_proxy_nodes == {"G": "node-b"}


def test_sort_by_latency_orders_nodes(qtbot):
    page, _proxy, _settings, _group = _page(qtbot)
    page._sort_check.setChecked(True)
    labels = [page._node_list.item(i).text() for i in range(page._node_list.count())]
    assert labels[0].startswith("●  node-a")
    assert "node-b" in labels[1]
