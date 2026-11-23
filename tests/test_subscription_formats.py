import base64

import pytest

from mihomo_lite.config.loader import load_yaml_text, looks_like_link_subscription
from mihomo_lite.core import profile_manager
from mihomo_lite.utils.exceptions import ConfigError

PROFILE = """proxies:
  - name: a
    type: socks5
    server: 127.0.0.1
    port: 1
rules:
  - MATCH,DIRECT
"""


def test_plain_yaml_still_works():
    data = load_yaml_text(PROFILE)
    assert data["proxies"][0]["name"] == "a"


def test_base64_wrapped_profile_is_decoded():
    encoded = base64.b64encode(PROFILE.encode()).decode()
    data = load_yaml_text(encoded)
    assert data["proxies"][0]["name"] == "a"


def test_base64_link_list_is_explained():
    links = "ss://YWVzLTEyOC1nY206cGFzcw@1.2.3.4:443#node1\nvmess://eyJhZGQiOiIxLjIuMy40In0=\n"
    encoded = base64.b64encode(links.encode()).decode()
    with pytest.raises(ConfigError) as info:
        load_yaml_text(encoded)
    assert "proxy links" in str(info.value)


def test_plain_link_list_is_explained():
    links = "ss://YWVzLTEyOC1nY206cGFzcw@1.2.3.4:443#node1\n"
    with pytest.raises(ConfigError) as info:
        load_yaml_text(links)
    assert "proxy links" in str(info.value)


def test_unknown_scalar_is_rejected():
    with pytest.raises(ConfigError) as info:
        load_yaml_text("not a profile at all")
    assert "Clash" in str(info.value) or "mapping" in str(info.value)


LINKS = "ss://YWVzLTEyOC1nY206cGFzcw@1.2.3.4:443#node1\n"


def test_looks_like_links_raw_and_base64():
    assert looks_like_link_subscription(LINKS)
    assert looks_like_link_subscription(base64.b64encode(LINKS.encode()).decode())
    assert not looks_like_link_subscription(PROFILE)


class _Response:
    status_code = 200

    def __init__(self, payload):
        self._payload = payload

    def iter_bytes(self):
        yield self._payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _Client:
    def __init__(self, *args, **kwargs):
        self.user_agent = kwargs.get("headers", {}).get("User-Agent", "")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def stream(self, method, url):
        if "clash" in self.user_agent.lower():
            return _Response(PROFILE.encode())
        return _Response(base64.b64encode(LINKS.encode()))


def test_fetch_retries_with_clash_user_agent(monkeypatch):
    monkeypatch.setattr(profile_manager.httpx, "Client", _Client)
    text = profile_manager.fetch_subscription("https://example.test/sub")
    assert "proxies:" in text


def test_fetch_explains_when_every_agent_gets_links(monkeypatch):
    class LinksOnly(_Client):
        def stream(self, method, url):
            return _Response(base64.b64encode(LINKS.encode()))

    monkeypatch.setattr(profile_manager.httpx, "Client", LinksOnly)
    with pytest.raises(ConfigError) as info:
        profile_manager.fetch_subscription("https://example.test/sub")
    assert "link list" in str(info.value)


def test_html_is_rejected_with_hint():
    with pytest.raises(ConfigError) as info:
        load_yaml_text("<html><body>login</body></html>")
    assert "HTML" in str(info.value)
