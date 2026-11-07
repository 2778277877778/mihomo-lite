import httpx
import pytest

from mihomo_lite.mihomo.api import MihomoAPI
from mihomo_lite.models.proxy import parse_proxies
from mihomo_lite.utils.exceptions import ApiError


def make_api(handler):
    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport, base_url="http://127.0.0.1:9090")
    return MihomoAPI("http://127.0.0.1:9090", "secret", client=client)


def test_version_parsing():
    api = make_api(lambda request: httpx.Response(200, json={"version": "v1.19.33"}))
    assert api.version()["version"] == "v1.19.33"


def test_authorization_header_is_sent():
    seen = {}

    def handler(request):
        seen["auth"] = request.headers.get("Authorization")
        return httpx.Response(200, json={"version": "x"})

    make_api(handler).version()
    assert seen["auth"] == "Bearer secret"


def test_http_error_becomes_api_error():
    api = make_api(lambda request: httpx.Response(401, text="unauthorized"))
    with pytest.raises(ApiError) as info:
        api.version()
    assert info.value.status == 401


def test_connection_error_becomes_api_error():
    def handler(request):
        raise httpx.ConnectError("refused")

    with pytest.raises(ApiError) as info:
        make_api(handler).version()
    assert "not reachable" in str(info.value)


def test_timeout_becomes_api_error():
    def handler(request):
        raise httpx.ReadTimeout("slow")

    with pytest.raises(ApiError):
        make_api(handler).version()


def test_select_proxy_sends_put():
    calls = []

    def handler(request):
        calls.append((request.method, request.url.path, request.content))
        return httpx.Response(204)

    make_api(handler).select_proxy("G", "node")
    method, path, body = calls[0]
    assert method == "PUT"
    assert path == "/proxies/G"
    assert b"node" in body


def test_group_delay_parses_ints():
    api = make_api(
        lambda request: httpx.Response(200, json={"a": 120, "b": "80", "c": None})
    )
    assert api.group_delay("G", "http://test") == {"a": 120, "b": 80}


def test_parse_proxies_splits_groups_and_nodes():
    payload = {
        "proxies": {
            "GLOBAL": {"type": "Selector", "now": "G", "all": ["G", "DIRECT"]},
            "G": {"type": "Selector", "now": "node-a", "all": ["node-a", "node-b"]},
            "auto": {"type": "URLTest", "now": "node-a", "all": ["node-a"], "history": []},
            "node-a": {"type": "Shadowsocks", "history": [{"delay": 45}]},
            "node-b": {"type": "Vmess", "history": [{"delay": 0}]},
            "DIRECT": {"type": "Direct"},
        }
    }
    groups, nodes = parse_proxies(payload)
    names = {group.name for group in groups}
    assert names == {"GLOBAL", "G", "auto"}
    assert set(nodes) == {"node-a", "node-b"}
    assert nodes["node-a"].delay_ms == 45
    assert nodes["node-a"].delay_label == "45 ms"
    assert nodes["node-b"].delay_label == "timeout"


def test_parse_proxies_tolerates_garbage():
    assert parse_proxies({}) == ([], {})
    assert parse_proxies({"proxies": []}) == ([], {})
