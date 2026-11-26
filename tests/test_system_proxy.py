from mihomo_lite.system.proxy import (
    PROXY_TYPE_DIRECT,
    PROXY_TYPE_PROXY,
    ProxyState,
    SystemProxy,
    describe_foreign_proxy,
)


class FakeBackend:
    def __init__(self, state=None):
        self.state = state or ProxyState(flags=PROXY_TYPE_DIRECT)
        self.writes = []

    def read(self):
        return self.state

    def write(self, state):
        self.writes.append(state)
        self.state = state


def make_proxy(paths, backend, pid=4242, checker=lambda _pid: False):
    return SystemProxy(
        paths.proxy_journal,
        backend=backend,
        owner_pid=pid,
        process_checker=checker,
    )


def test_apply_points_at_local_server_and_journals(paths):
    backend = FakeBackend(ProxyState(flags=PROXY_TYPE_PROXY, server="127.0.0.1:7897"))
    proxy = make_proxy(paths, backend)

    proxy.apply("127.0.0.1:23456", "localhost")

    assert backend.state.server == "127.0.0.1:23456"
    assert backend.state.enabled
    assert backend.state.bypass == "localhost"
    assert paths.proxy_journal.exists()
    assert proxy.owns_system_proxy()


def test_restore_returns_the_original_state(paths):
    original = ProxyState(flags=PROXY_TYPE_PROXY, server="127.0.0.1:7897", bypass="a;b")
    backend = FakeBackend(original)
    proxy = make_proxy(paths, backend)

    proxy.apply("127.0.0.1:5000")
    assert proxy.restore() is True

    assert backend.state == original
    assert not paths.proxy_journal.exists()
    assert proxy.restore() is False


def test_dead_ephemeral_loopback_snapshot_becomes_direct(paths, monkeypatch):
    monkeypatch.setattr("mihomo_lite.system.proxy._loopback_alive", lambda _server: False)
    original = ProxyState(flags=PROXY_TYPE_PROXY, server="127.0.0.1:49774")
    backend = FakeBackend(original)
    proxy = make_proxy(paths, backend)

    proxy.apply("127.0.0.1:50000")
    assert proxy.restore() is True

    assert not backend.state.enabled
    assert backend.state.server == ""


def test_dead_ephemeral_journal_is_not_restored(paths, monkeypatch):
    monkeypatch.setattr("mihomo_lite.system.proxy._loopback_alive", lambda _server: False)
    original = ProxyState(flags=PROXY_TYPE_PROXY, server="127.0.0.1:49774")
    backend = FakeBackend(original)
    make_proxy(paths, backend, pid=333).apply("127.0.0.1:50000")

    restarted = make_proxy(paths, backend, pid=444, checker=lambda _pid: False)
    assert restarted.recover_if_stale() == "restored"
    assert not backend.state.enabled
    assert backend.state.server == ""


def test_conventional_loopback_proxy_is_still_restored(paths, monkeypatch):
    monkeypatch.setattr("mihomo_lite.system.proxy._loopback_alive", lambda _server: False)
    original = ProxyState(flags=PROXY_TYPE_PROXY, server="127.0.0.1:7897")
    backend = FakeBackend(original)
    proxy = make_proxy(paths, backend)

    proxy.apply("127.0.0.1:50000")
    proxy.restore()

    assert backend.state == original


def test_repair_stale_loopback_clears_a_dead_proxy(paths, monkeypatch):
    monkeypatch.setattr("mihomo_lite.system.proxy._loopback_alive", lambda _server: False)
    backend = FakeBackend(ProxyState(flags=PROXY_TYPE_PROXY, server="127.0.0.1:49774"))
    proxy = make_proxy(paths, backend)

    assert proxy.repair_stale_loopback() is True
    assert not backend.state.enabled
    assert proxy.repair_stale_loopback() is False


def test_second_apply_keeps_the_first_snapshot(paths):
    original = ProxyState(flags=PROXY_TYPE_PROXY, server="127.0.0.1:7897")
    backend = FakeBackend(original)
    proxy = make_proxy(paths, backend)

    proxy.apply("127.0.0.1:5000")
    proxy.apply("127.0.0.1:5001")
    proxy.restore()

    assert backend.state.server == "127.0.0.1:7897"


def test_recovery_restores_when_the_owner_is_gone(paths):
    original = ProxyState(flags=PROXY_TYPE_PROXY, server="127.0.0.1:7897")
    backend = FakeBackend(original)
    make_proxy(paths, backend, pid=111).apply("127.0.0.1:5000")

    restarted = make_proxy(paths, backend, pid=222, checker=lambda _pid: False)
    assert restarted.recover_if_stale() == "restored"
    assert backend.state.server == "127.0.0.1:7897"
    assert not paths.proxy_journal.exists()


def test_recovery_leaves_a_live_owner_alone(paths):
    backend = FakeBackend(ProxyState(flags=PROXY_TYPE_PROXY, server="127.0.0.1:7897"))
    make_proxy(paths, backend, pid=111).apply("127.0.0.1:5000")

    other = make_proxy(paths, backend, pid=222, checker=lambda pid: pid == 111)
    assert other.recover_if_stale() == "active"
    assert backend.state.server == "127.0.0.1:5000"


def test_corrupt_journal_is_discarded(paths):
    paths.proxy_journal.write_text("{not json", encoding="utf-8")
    backend = FakeBackend()
    proxy = make_proxy(paths, backend)
    assert proxy.recover_if_stale() == "none"
    assert not paths.proxy_journal.exists()


def test_describe_foreign_proxy_only_warns_for_others():
    enabled = ProxyState(flags=PROXY_TYPE_PROXY, server="127.0.0.1:7897")
    message = describe_foreign_proxy(enabled, "127.0.0.1:23456")
    assert message is not None and "7897" in message

    assert describe_foreign_proxy(enabled, "127.0.0.1:7897") is None
    assert describe_foreign_proxy(ProxyState(), "127.0.0.1:23456") is None


def test_disabled_state_clears_the_server():
    state = ProxyState(flags=PROXY_TYPE_PROXY, server="1.2.3.4:80").disabled()
    assert not state.enabled
    assert state.server == ""


def test_state_roundtrip():
    state = ProxyState(flags=3, server="127.0.0.1:1", bypass="x", autoconfig_url="http://pac")
    assert ProxyState.from_dict(state.to_dict()) == state
