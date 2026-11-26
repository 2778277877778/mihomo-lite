"""Runtime-copy generation with the optional download listeners."""

from __future__ import annotations

import pytest

from mihomo_lite.config.download_listeners import DownloadListener
from mihomo_lite.config.generator import generate_runtime_config
from mihomo_lite.utils.exceptions import ConfigError


def _generate(profile, **kwargs):
    return generate_runtime_config(profile, mixed_port=24567, api_port=24568, secret="s", **kwargs)


def test_both_switches_off_keeps_the_old_runtime_copy(sample_profile):
    baseline = _generate(sample_profile)
    disabled = _generate(sample_profile, download_listeners=None, extra_proxies=None)
    assert baseline.to_yaml() == disabled.to_yaml()
    assert "listeners" not in disabled.data


def test_old_profile_listeners_are_still_removed_when_disabled(sample_profile):
    sample_profile["listeners"] = [{"name": "extra", "type": "http", "port": 9999}]
    generated = _generate(sample_profile)
    assert "listeners" not in generated.data


def test_enabled_listeners_are_loopback_mixed(sample_profile):
    listeners = (
        DownloadListener(name="ml-download-1", node="node-a", port=24601),
        DownloadListener(name="ml-download-2", node="node-b", port=24602),
    )
    generated = _generate(sample_profile, download_listeners=listeners)
    assert generated.data["listeners"] == [
        {
            "name": "ml-download-1",
            "type": "mixed",
            "listen": "127.0.0.1",
            "port": 24601,
            "proxy": "node-a",
            "udp": False,
        },
        {
            "name": "ml-download-2",
            "type": "mixed",
            "listen": "127.0.0.1",
            "port": 24602,
            "proxy": "node-b",
            "udp": False,
        },
    ]
    assert any("multi-node" in note for note in generated.notes)


def test_extra_proxy_from_another_profile_is_appended(sample_profile):
    extra = {"name": "node-c", "type": "socks5", "server": "127.0.0.1", "port": 1081}
    listeners = (DownloadListener(name="ml-download-1", node="node-c", port=24603),)
    generated = _generate(
        sample_profile, download_listeners=listeners, extra_proxies=[extra]
    )
    names = [proxy["name"] for proxy in generated.data["proxies"]]
    assert names == ["node-a", "node-b", "node-c"]
    assert sample_profile["proxies"][-1]["name"] == "node-b"


def test_extra_proxy_conflict_is_rejected(sample_profile):
    extra = {"name": "node-a", "type": "http", "server": "127.0.0.1", "port": 9}
    listeners = (DownloadListener(name="ml-download-1", node="node-a", port=24604),)
    with pytest.raises(ConfigError):
        _generate(sample_profile, download_listeners=listeners, extra_proxies=[extra])


def test_missing_selected_node_is_rejected(sample_profile):
    listeners = (DownloadListener(name="ml-download-1", node="ghost", port=24605),)
    with pytest.raises(ConfigError):
        _generate(sample_profile, download_listeners=listeners)


def test_disabled_run_does_not_add_extra_proxies(sample_profile):
    extra = {"name": "node-c", "type": "socks5", "server": "127.0.0.1", "port": 1081}
    generated = _generate(sample_profile, extra_proxies=[extra])
    assert [proxy["name"] for proxy in generated.data["proxies"]] == ["node-a", "node-b"]
