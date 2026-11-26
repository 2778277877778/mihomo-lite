"""Conditional listener generation for multi-node downloads."""

from __future__ import annotations

import pytest

from mihomo_lite.config.download_listeners import DownloadListener, allocate_download_listeners
from mihomo_lite.utils.exceptions import ConfigError


def test_no_nodes_means_no_listeners():
    assert allocate_download_listeners([]) == ()
    assert allocate_download_listeners(["", "   "]) == ()


def test_listener_config_is_loopback_mixed_tcp():
    ports = iter([41001, 41002])
    listeners = allocate_download_listeners(
        ["node-a", "node-b"], port_picker=lambda _avoid: next(ports)
    )
    assert [listener.node for listener in listeners] == ["node-a", "node-b"]
    assert [listener.port for listener in listeners] == [41001, 41002]
    first = listeners[0].to_config()
    assert first == {
        "name": "ml-download-1",
        "type": "mixed",
        "listen": "127.0.0.1",
        "port": 41001,
        "proxy": "node-a",
        "udp": False,
    }


def test_port_collision_retries_with_a_new_port():
    ports = iter([41001, 41001, 41002, 41003])
    listeners = allocate_download_listeners(
        ["node-a", "node-b"], avoid={41001}, port_picker=lambda _avoid: next(ports)
    )
    assert [listener.port for listener in listeners] == [41002, 41003]
    assert listeners[0].name == "ml-download-1"


def test_avoid_ports_are_not_reused():
    seen: list[set[int]] = []

    def picker(avoid: set[int]) -> int:
        seen.append(set(avoid))
        return 42000 + len(seen)

    listeners = allocate_download_listeners(["a", "b", "c"], avoid={42000}, port_picker=picker)
    assert [listener.port for listener in listeners] == [42001, 42002, 42003]
    assert 42000 in seen[0]
    assert 42001 in seen[1]


def test_duplicate_node_names_are_collapsed():
    ports = iter([43001, 43002])
    listeners = allocate_download_listeners(
        ["a", "a", "b"], port_picker=lambda _avoid: next(ports)
    )
    assert [listener.node for listener in listeners] == ["a", "b"]


def test_picker_oserror_becomes_config_error():
    def broken(_avoid: set[int]) -> int:
        raise OSError("no ports")

    with pytest.raises(ConfigError):
        allocate_download_listeners(["a"], port_picker=broken)


def test_listener_dataclass_is_hashable():
    listener = DownloadListener(name="x", node="a", port=1)
    assert {listener} == {DownloadListener(name="x", node="a", port=1)}
