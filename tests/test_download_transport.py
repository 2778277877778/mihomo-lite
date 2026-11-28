"""Client caching in the HTTP transport."""

from __future__ import annotations

from mihomo_lite.download import transport as transport_module


class FakeClient:
    def __init__(self, port: int) -> None:
        self.port = port
        self.closed = False

    def close(self) -> None:
        self.closed = True


def test_clients_are_reused_per_proxy_port(monkeypatch):
    created: list[FakeClient] = []

    def fake_client(port: int, timeout: float) -> FakeClient:
        client = FakeClient(port)
        created.append(client)
        return client

    monkeypatch.setattr(transport_module, "_client", fake_client)
    transport = transport_module.HttpxTransport()
    try:
        first = transport._client(50001)
        again = transport._client(50001)
        other = transport._client(50002)
    finally:
        transport.close()

    assert first is again
    assert first is not other
    assert len(created) == 2
    assert all(client.closed for client in created)
