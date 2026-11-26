"""Connection-manager integration for conditional download listeners."""

from __future__ import annotations

import json

import yaml
from PySide6.QtCore import QObject, Signal

from mihomo_lite.core.connection_manager import ConnectionManager
from mihomo_lite.core.download_catalog import DownloadCatalog
from mihomo_lite.core.profile_manager import ProfileManager
from mihomo_lite.core.state_manager import SettingsStore
from mihomo_lite.mihomo.core_manager import CoreInfo
from mihomo_lite.models.app_state import ConnectionState

P1 = """
proxies:
  - name: n1
    type: socks5
    server: 127.0.0.1
    port: 1080
proxy-groups:
  - name: G
    type: select
    proxies: [n1, DIRECT]
rules:
  - MATCH,G
"""

P2 = """
proxies:
  - name: n2
    type: http
    server: 127.0.0.1
    port: 8080
proxy-groups:
  - name: G2
    type: select
    proxies: [n2, DIRECT]
rules:
  - MATCH,G2
"""


class FakeProcess(QObject):
    started = Signal(int)
    stopped = Signal(int, bool)
    output = Signal(str)
    failed = Signal(str)

    def __init__(self):
        super().__init__()
        self.running = False
        self.pid = 0
        self.start_calls = 0

    def start(self, core, config, workdir, extra_env=None):
        self.start_calls += 1
        self.running = True
        self.pid = 4242
        self.started.emit(self.pid)
        return True

    def stop(self, **kwargs):
        self.running = False
        self.stopped.emit(0, False)

    def kill_now(self, *args, **kwargs):
        self.running = False


class FakeAPI:
    def __init__(self):
        self.reload_calls = []
        self.closed = False

    def version(self):
        return {"version": "v-test"}

    def reload_config(self, path):
        self.reload_calls.append(path)

    def close(self):
        self.closed = True


class FakeCore:
    def ensure(self):
        return CoreInfo(path="mihomo.exe", version="v-test", source="test")


class FakeTraffic(QObject):
    sample = Signal(object)
    link_changed = Signal(bool, str)

    def start(self, port, secret):
        self.port = port

    def stop(self):
        pass


def _harness(paths, qapp):
    settings = SettingsStore(paths)
    settings.load()
    profiles = ProfileManager(paths)
    active = profiles.import_text(P1, name="First")
    other = profiles.import_text(P2, name="Second")
    api = FakeAPI()
    connection = ConnectionManager(
        paths,
        settings,
        profiles,
        process=FakeProcess(),
        core=FakeCore(),
        api_factory=lambda *args, **kwargs: api,
        traffic=FakeTraffic(),
        catalog=DownloadCatalog(profiles),
    )
    return connection, settings, profiles, active, other, api


def _wait_connected(qtbot, connection):
    qtbot.waitUntil(lambda: connection.state is ConnectionState.CONNECTED, timeout=4000)


def test_both_switches_off_produces_no_listeners(paths, qapp, qtbot):
    connection, _settings, _profiles, _active, _other, _api = _harness(paths, qapp)
    connection.connect()
    _wait_connected(qtbot, connection)

    assert connection.session is not None
    assert connection.session.download_listeners == ()
    runtime = yaml.safe_load(paths.runtime_config.read_text(encoding="utf-8"))
    assert "listeners" not in runtime
    session = json.loads(paths.session_file.read_text(encoding="utf-8"))
    assert "download_listeners" not in session


def test_multi_node_switch_on_generates_loopback_listeners(paths, qapp, qtbot):
    connection, settings, _profiles, _active, other, _api = _harness(paths, qapp)
    settings.update(
        download_multithreaded=True,
        download_multi_node=True,
        download_nodes=[f"{other.id}::n2"],
    )
    connection.connect()
    _wait_connected(qtbot, connection)

    session = connection.session
    assert session is not None
    assert len(session.download_listeners) == 1
    listener = session.download_listeners[0]
    assert listener.node == "n2"
    assert listener.port != session.mixed_port
    assert listener.port != session.api_port

    runtime = yaml.safe_load(paths.runtime_config.read_text(encoding="utf-8"))
    assert runtime["listeners"] == [
        {
            "name": listener.name,
            "type": "mixed",
            "listen": "127.0.0.1",
            "port": listener.port,
            "proxy": "n2",
            "udp": False,
        }
    ]
    assert any(proxy["name"] == "n2" for proxy in runtime["proxies"])


def test_multi_node_without_multithread_stays_off(paths, qapp, qtbot):
    connection, settings, _profiles, _active, other, _api = _harness(paths, qapp)
    settings.update(download_multi_node=True, download_nodes=[f"{other.id}::n2"])
    assert settings.current.download_multi_node is False
    connection.connect()
    _wait_connected(qtbot, connection)
    assert connection.session is not None
    assert connection.session.download_listeners == ()


def test_disabled_features_never_resolve_the_catalog(paths, qapp, qtbot, monkeypatch):
    connection, _settings, _profiles, _active, _other, _api = _harness(paths, qapp)

    def boom(*args, **kwargs):
        raise AssertionError("the download catalog must not be used while both switches are off")

    monkeypatch.setattr(connection._catalog, "resolve", boom)
    connection.connect()
    _wait_connected(qtbot, connection)
    assert connection.session is not None
    assert connection.session.download_listeners == ()


def test_conflicting_selection_fails_connect(paths, qapp, qtbot):
    connection, settings, _profiles, _active, _other, _api = _harness(paths, qapp)
    settings.update(
        download_multithreaded=True,
        download_multi_node=True,
        download_nodes=["missing::node"],
    )
    connection.connect()
    qtbot.waitUntil(lambda: connection.state is ConnectionState.ERROR, timeout=4000)
    assert connection.session is None


def test_reload_applies_listeners_and_updates_session(paths, qapp, qtbot):
    connection, settings, _profiles, _active, other, api = _harness(paths, qapp)
    connection.connect()
    _wait_connected(qtbot, connection)
    assert connection.session is not None
    assert connection.session.download_listeners == ()

    settings.update(
        download_multithreaded=True,
        download_multi_node=True,
        download_nodes=[f"{other.id}::n2"],
    )
    assert connection.reload_active_config() is True
    qtbot.waitUntil(lambda: bool(api.reload_calls), timeout=3000)
    qtbot.waitUntil(
        lambda: connection.session is not None
        and len(connection.session.download_listeners) == 1,
        timeout=3000,
    )
    runtime = yaml.safe_load(paths.runtime_config.read_text(encoding="utf-8"))
    assert runtime["listeners"][0]["listen"] == "127.0.0.1"
