from pathlib import Path

import httpx
import pytest
from PySide6.QtCore import QObject, Signal

from mihomo_lite.core import profile_manager as pm
from mihomo_lite.core.connection_manager import ConnectionManager
from mihomo_lite.core.profile_manager import ProfileManager
from mihomo_lite.core.state_manager import SettingsStore
from mihomo_lite.mihomo.core_manager import CoreInfo
from mihomo_lite.models.app_state import ConnectionState
from mihomo_lite.system.proxy import PROXY_TYPE_DIRECT, ProxyState, SystemProxy
from mihomo_lite.system.single_instance import SingleInstance
from mihomo_lite.utils.exceptions import ConfigError
from mihomo_lite.utils.logger import redact_url

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


# -- single instance -------------------------------------------------------
def test_lock_retry_waits_for_the_previous_instance(tmp_path, qapp):
    lock = tmp_path / "instance.lock"
    first = SingleInstance(lock)
    assert first.is_primary

    second = SingleInstance(lock)
    assert not second.is_primary
    assert second.wait_for_primary(timeout_ms=250, interval_ms=50) is False

    first.release()
    assert second.wait_for_primary(timeout_ms=1500, interval_ms=50) is True
    second.release()


# -- redaction -------------------------------------------------------------
def test_redact_url_masks_common_secret_parameters():
    masked = redact_url("https://sub.example/x?token=abc123&key=zzz&lang=zh")
    assert "abc123" not in masked
    assert "zzz" not in masked
    assert "sub.example" in masked
    assert "lang=zh" in masked


def test_subscription_error_hides_the_token(monkeypatch):
    class Boom:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            return False

        def stream(self, *args, **kwargs):
            raise httpx.ConnectError(
                "connection failed for https://sub.example/api?token=SUPERSECRET"
            )

    monkeypatch.setattr(pm.httpx, "Client", Boom)
    with pytest.raises(ConfigError) as info:
        pm.fetch_subscription("https://sub.example/api?token=SUPERSECRET")
    assert "SUPERSECRET" not in str(info.value)
    assert "***" in str(info.value)


# -- TUN health ------------------------------------------------------------
class FakeBackend:
    def __init__(self):
        self.state = ProxyState(flags=PROXY_TYPE_DIRECT)

    def read(self):
        return self.state

    def write(self, state):
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

    def start(self, *args, **kwargs):
        self.running = True
        self.pid = 1
        self.started.emit(1)
        return True

    def stop(self, **kwargs):
        self.running = False
        self.stopped.emit(0, False)

    def kill_now(self, *args, **kwargs):
        self.running = False


class FakeAPI:
    def __init__(self):
        self.reload_calls = []

    def version(self):
        return {"version": "v-test"}

    def close(self):
        pass

    def reload_config(self, path):
        self.reload_calls.append(path)


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
def connection(paths, qapp):
    settings = SettingsStore(paths)
    settings.load()
    profiles = ProfileManager(paths)
    source = paths.root / "p.yaml"
    source.write_text(PROFILE, encoding="utf-8")
    profiles.import_file(source, name="P")
    api = FakeAPI()
    conn = ConnectionManager(
        paths,
        settings,
        profiles,
        process=FakeProcess(),
        proxy=SystemProxy(paths.proxy_journal, backend=FakeBackend()),
        core=FakeCore(),
        api_factory=lambda *a, **k: api,
        traffic=FakeTraffic(),
    )
    return conn, api, settings


def test_reload_rewrites_and_asks_the_core(connection, qtbot, monkeypatch):
    conn, api, _settings = connection
    monkeypatch.setattr("mihomo_lite.system.elevation.is_admin", lambda: True)
    conn.connect()
    qtbot.waitUntil(lambda: conn.state is ConnectionState.CONNECTED, timeout=4000)

    assert conn.reload_active_config() is True
    qtbot.waitUntil(lambda: bool(api.reload_calls), timeout=2000)
    assert api.reload_calls[0].endswith("generated.yaml")
    assert "MATCH,G" in conn._paths.runtime_config.read_text(encoding="utf-8")


def test_reload_is_ignored_while_disconnected(connection):
    conn, _api, _settings = connection
    assert conn.reload_active_config() is False


def test_tun_health_reports_core_errors(connection, qtbot):
    conn, _api, _settings = connection
    conn._mode = "tun"
    conn._state = ConnectionState.CONNECTED
    warnings = []
    conn.warning.connect(warnings.append)

    conn._on_core_output('level=error msg="Start TUN listening failed: wintun not found"')
    conn._verify_tun_started()

    assert warnings and "TUN did not start" in warnings[-1]


def test_tun_health_accepts_a_started_device(connection):
    conn, _api, _settings = connection
    conn._mode = "tun"
    conn._state = ConnectionState.CONNECTED
    warnings = []
    conn.warning.connect(warnings.append)

    conn._on_core_output('level=info msg="TUN listening at: MihomoLite"')
    conn._verify_tun_started()

    assert warnings == []
