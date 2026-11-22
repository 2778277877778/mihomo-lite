from mihomo_lite.core import net_tools


def test_speed_mbps_math():
    assert net_tools.speed_mbps(1_000_000, 1.0) == 8.0
    assert net_tools.speed_mbps(0, 1.0) == 0.0
    assert net_tools.speed_mbps(1000, 0) == 0.0


def test_fetch_public_ip_uses_the_first_answer(monkeypatch):
    class Response:
        status_code = 200
        text = "203.0.113.7\n"

    class Client:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def get(self, url):
            return Response()

    monkeypatch.setattr(net_tools.httpx, "Client", Client)
    result = net_tools.fetch_public_ip("127.0.0.1:7890")
    assert result.address == "203.0.113.7"
    assert result.source == "api.ip.sb"


def test_fetch_public_ip_reports_failure(monkeypatch):
    class Client:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def get(self, url):
            raise net_tools.httpx.ConnectError("refused")

    monkeypatch.setattr(net_tools.httpx, "Client", Client)
    try:
        net_tools.fetch_public_ip(None)
    except RuntimeError as exc:
        assert "could not detect" in str(exc)
    else:
        raise AssertionError("expected RuntimeError")
