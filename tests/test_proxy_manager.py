"""Batch latency tests and proxy history persistence."""

from __future__ import annotations

from mihomo_lite.core.proxy_manager import ProxyManager
from mihomo_lite.core.state_manager import SettingsStore
from mihomo_lite.models.app_state import AppSettings
from mihomo_lite.models.proxy import ProxyGroup, ProxyNode
from mihomo_lite.utils.tasks import TaskRunner


class FakeAPI:
    def proxy_delay(self, name: str, url: str, *, timeout_ms: int = 5000) -> int:
        return {"a": 120, "b": 240, "bad": 0}.get(name, 0)


def test_batch_latency_tests_all_nodes_and_updates_groups(qapp, qtbot):
    manager = ProxyManager(lambda: FakeAPI(), TaskRunner())
    group = ProxyGroup(name="G", type="Selector", now="a", members=["a", "b", "DIRECT"])
    manager._nodes = {"a": ProxyNode("a"), "b": ProxyNode("b")}
    manager._groups = [group]
    finished: list[object] = []
    manager.batch_delay_finished.connect(finished.append)

    assert manager.test_all_delays() is True
    qtbot.waitUntil(lambda: bool(finished), timeout=5000)

    assert manager.batch_running is False
    assert finished[0] == {"a": 120, "b": 240}
    assert manager.stats["a"]["delay"] == 120
    assert group.delays["a"] == 120
    assert group.delays["b"] == 240


def test_batch_latency_ignores_a_failing_node(qapp, qtbot):
    class FlakyAPI(FakeAPI):
        def proxy_delay(self, name: str, url: str, *, timeout_ms: int = 5000) -> int:
            if name == "bad":
                raise RuntimeError("timeout")
            return super().proxy_delay(name, url, timeout_ms=timeout_ms)

    manager = ProxyManager(lambda: FlakyAPI(), TaskRunner())
    manager._nodes = {"a": ProxyNode("a"), "bad": ProxyNode("bad")}
    finished: list[object] = []
    manager.batch_delay_finished.connect(finished.append)

    assert manager.test_all_delays() is True
    qtbot.waitUntil(lambda: bool(finished), timeout=5000)
    assert finished[0] == {"a": 120}


def test_last_proxy_nodes_are_persisted(paths, qapp):
    store = SettingsStore(paths)
    store.load()
    store.update(last_proxy_nodes={"G": "node-a"})

    reopened = SettingsStore(paths)
    loaded = reopened.load()
    assert loaded.last_proxy_nodes == {"G": "node-a"}
    assert AppSettings().last_proxy_nodes == {}
