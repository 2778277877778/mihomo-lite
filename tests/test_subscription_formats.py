import base64

import pytest

from mihomo_lite.config.loader import load_yaml_text
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


def test_html_is_rejected_with_hint():
    with pytest.raises(ConfigError) as info:
        load_yaml_text("<html><body>login</body></html>")
    assert "HTML" in str(info.value)
