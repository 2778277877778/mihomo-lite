"""Cross-profile node catalogue for multi-node downloads."""

from __future__ import annotations

import pytest

from mihomo_lite.core.download_catalog import DownloadCatalog
from mihomo_lite.core.profile_manager import ProfileManager
from mihomo_lite.utils.exceptions import ConfigError


def _yaml(nodes: str) -> str:
    return f"""proxies:
{nodes}
proxy-groups:
  - name: G
    type: select
    proxies: [n1, DIRECT]
rules:
  - MATCH,G
"""


P1 = _yaml("""  - name: n1
    type: socks5
    server: 127.0.0.1
    port: 1080
  - name: shared
    type: socks5
    server: 127.0.0.1
    port: 1081
""")

P2 = _yaml("""  - name: n2
    type: http
    server: 127.0.0.1
    port: 8080
  - name: shared
    type: socks5
    server: 127.0.0.1
    port: 1081
""")

P3_CONFLICT = _yaml("""  - name: shared
    type: http
    server: 127.0.0.1
    port: 9999
""")


@pytest.fixture
def catalog(paths, qapp):
    profiles = ProfileManager(paths)
    first = profiles.import_text(P1, name="First")
    second = profiles.import_text(P2, name="Second")
    return DownloadCatalog(profiles), profiles, first, second


def test_catalog_lists_nodes_from_every_profile(catalog):
    nodes, _profiles, first, second = catalog
    entries = nodes.nodes()
    keys = {entry.key for entry in entries}
    assert f"{first.id}::n1" in keys
    assert f"{second.id}::n2" in keys
    assert any(entry.profile_name == "Second" for entry in entries)


def test_resolve_appends_nodes_from_another_profile(catalog):
    nodes, profiles, _first, second = catalog
    active = profiles.load_active_config()
    extras, names = nodes.resolve([f"{second.id}::n2"], active)
    assert names == ["n2"]
    assert extras == [
        {"name": "n2", "type": "http", "server": "127.0.0.1", "port": 8080}
    ]


def test_resolve_uses_active_definition_without_extra(catalog):
    nodes, profiles, first, _second = catalog
    active = profiles.load_active_config()
    extras, names = nodes.resolve([f"{first.id}::n1"], active)
    assert names == ["n1"]
    assert extras == []


def test_identical_duplicate_names_are_allowed(catalog):
    nodes, profiles, _first, second = catalog
    entry = next(item for item in nodes.nodes() if item.key == f"{second.id}::shared")
    assert entry.conflict is False
    extras, names = nodes.resolve([f"{second.id}::shared"], profiles.load_active_config())
    assert names == ["shared"]
    assert extras == []


def test_different_duplicate_names_are_marked_and_rejected(paths, qapp):
    profiles = ProfileManager(paths)
    profiles.import_text(P1, name="First")
    conflict = profiles.import_text(P3_CONFLICT, name="Conflict")
    nodes = DownloadCatalog(profiles)
    entry = next(item for item in nodes.nodes() if item.key == f"{conflict.id}::shared")
    assert entry.conflict is True
    with pytest.raises(ConfigError):
        nodes.resolve([entry.key], profiles.load_active_config())


def test_unknown_selection_is_rejected(catalog):
    nodes, profiles, _first, _second = catalog
    with pytest.raises(ConfigError):
        nodes.resolve(["missing::node"], profiles.load_active_config())


def test_empty_selection_returns_nothing(catalog):
    nodes, profiles, _first, _second = catalog
    assert nodes.resolve([], profiles.load_active_config()) == ([], [])
