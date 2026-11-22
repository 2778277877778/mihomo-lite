from pathlib import Path

import pytest
from PySide6.QtCore import QObject, Signal

from mihomo_lite.config.generator import generate_runtime_config
from mihomo_lite.core.connection_manager import ConnectionManager
from mihomo_lite.core.profile_manager import ProfileManager
from mihomo_lite.core.state_manager import SettingsStore
from mihomo_lite.mihomo.core_manager import CoreInfo
from mihomo_lite.models.app_state import AppSettings, ConnectionState
from mihomo_lite.system.proxy import PROXY_TYPE_DIRECT, ProxyState, SystemProxy

PROFILE = """
proxies:
  - name: a
    type: socks5
    server: 127.0.0.1
    port: 1
proxy-groups:
  - name: G
    type: select
    proxies: [a, DIRECT]
rules:
  - MATCH,G
"""


def sample_profile():
    return {
        "proxies": [{"name": "a", "type": "socks5", "server": "127.0.0.1", "port": 1}],
        "proxy-groups": [{"name": "G", "type": "select", "proxies": ["a", "DIRECT"]}],
        "rules": ["MATCH,G"],
    }


def test_tun_section_is_generated():
    generated = generate_runtime_config(
        sample_profile(),
        mixed_port=1234,
        api_port=1235,
        secret="s",
        tun=True,
        tun_stack="gvisor",
    )
    tun = generated.data["tun"]
    assert tun["enable"] is True
    assert tun["stack"] == "gvisor"
    assert tun["auto-route"] is True
    assert tun["dns-hijack"] == ["any:53"]
    assert generated.data["dns"]["enable"] is True
    assert generated.data["dns"]["enhanced-mode"] == "fake-ip"
    assert any("TUN enabled" in note for note in generated.notes)


def test_tun_can_skip_dns_hijack():
    generated = generate_runtime_config(
        sample_profile(), mixed_port=1, api_port=2, secret="s", tun=True, tun_dns_hijack=False
    )
    assert "dns-hijack" not in generated.data["tun"]


def test_tun_off_disables_profile_tun_and_warns():
    profile = sample_profile()
    profile["tun"] = {"enable": True, "stack": "system"}
    generated = generate_runtime_config(profile, mixed_port=1, api_port=2, secret="s")
    assert generated.data["tun"] == {"enable": False}
    assert any("disabled in Settings" in note for note in generated.notes)


def test_tun_rejects_bad_stack_values_through_settings():
    with pytest.raises(ValueError):
        AppSettings(tun_stack="vpn")
    with pytest.raises(ValueError):
        AppSettings(auto_update_interval_hours=7)


class FakeBackend:
    def __init__(self):
        self.state = ProxyState(flags=PROXY_TYPE_DIRECT)
        self.writes = []

    def read(self):
        return self.state

    def write(self, state):
        self.writes.append(state)
        self.state = state


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
        self.pid = 777
        self.started.emit(self.pid)
        return True

    def stop(self, **kwargs):
        self.running = False
        self.stopped.emit(0, False)

    def kill_now(self, *args, **kwargs):
        self.running = False


class FakeAPI:
    def version(self):
        return {"version": "v-test"}

    def close(self):
        pass


class FakeCore:
    def ensure(self):
        return CoreInfo(path=Path("C:/fake/mihomo.exe"), version="v-test", source="test")


class FakeTraffic(QObject):
    sample = Signal(object)
    link_changed = Signal(bool, str)

    def start(self, port, secret):
        pass

    def stop(self):
        pass


@pytest.fixture
def base(paths, qapp):
    settings = SettingsStore(paths)
    settings.load()
    profiles = ProfileManager(paths)
    source = paths.root / "p.yaml"
    source.write_text(PROFILE, encoding="utf-8")
    profiles.import_file(source, name="P")
    backend = FakeBackend()
    process = FakeProcess()
    connection = ConnectionManager(
        paths,
        settings,
        profiles,
        process=process,
        proxy=SystemProxy(paths.proxy_journal, backend=backend),
        core=FakeCore(),
        api_factory=lambda *a, **k: FakeAPI(),
        traffic=FakeTraffic(),
    )
    return connection, settings, process, backend


def test_tun_without_admin_asks_for_elevation(base, qtbot, monkeypatch):
    connection, settings, process, _backend = base
    settings.update(tun_enabled=True)
    monkeypatch.setattr("mihomo_lite.system.elevation.is_admin", lambda: False)

    with qtbot.waitSignal(connection.elevation_required, timeout=2000):
        connection.connect()

    assert process.start_calls == 0
    assert connection.state is ConnectionState.STOPPED


def test_tun_without_wintun_fails_clearly(base, qtbot, monkeypatch):
    connection, settings, process, _backend = base
    settings.update(tun_enabled=True)
    monkeypatch.setattr("mihomo_lite.system.elevation.is_admin", lambda: True)
    monkeypatch.setattr("mihomo_lite.system.wintun.locate", lambda core: None)

    with qtbot.waitSignal(connection.error_changed, timeout=4000) as blocker:
        connection.connect()
    assert "wintun.dll" in blocker.args[0]
    assert process.start_calls == 0


def test_tun_connect_skips_the_system_proxy(base, qtbot, monkeypatch):
    connection, settings, _process, backend = base
    settings.update(tun_enabled=True)
    monkeypatch.setattr("mihomo_lite.system.elevation.is_admin", lambda: True)
    monkeypatch.setattr(
        "mihomo_lite.system.wintun.locate", lambda core: Path("C:/fake/wintun.dll")
    )

    connection.connect()
    qtbot.waitUntil(lambda: connection.state is ConnectionState.CONNECTED, timeout=5000)

    assert connection.session is not None
    assert connection.session.mode == "tun"
    assert not backend.state.enabled
    config = paths_runtime(connection)
    assert config["tun"]["enable"] is True


def paths_runtime(connection):
    import yaml

    return yaml.safe_load(connection._paths.runtime_config.read_text(encoding="utf-8"))
