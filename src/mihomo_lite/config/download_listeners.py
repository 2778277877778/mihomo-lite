"""Conditional runtime listeners used by multi-node downloads.

The listeners are only ever written into the hardened runtime copy, never into
the imported profile. They bind to loopback and pin one node per port so the
download scheduler can choose an egress without touching the controller.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass

from mihomo_lite.utils.exceptions import ConfigError
from mihomo_lite.utils.net import find_free_port

#: The official Mihomo name of the listener type that accepts HTTP and SOCKS.
LISTENER_TYPE = "mixed"
LISTENER_HOST = "127.0.0.1"


@dataclass(frozen=True)
class DownloadListener:
    """One loopback listener pinned to a proxy name."""

    name: str
    node: str
    port: int

    def to_config(self) -> dict[str, object]:
        # UDP is not needed for an HTTP download and disabling it avoids
        # colliding with another process that already owns the UDP port.
        return {
            "name": self.name,
            "type": LISTENER_TYPE,
            "listen": LISTENER_HOST,
            "port": self.port,
            "proxy": self.node,
            "udp": False,
        }


PortPicker = Callable[[set[int]], int]


def _default_picker(avoid: set[int]) -> int:
    return find_free_port(0, avoid=avoid)


def allocate_download_listeners(
    nodes: Sequence[str],
    *,
    avoid: Iterable[int] = (),
    port_picker: PortPicker | None = None,
) -> tuple[DownloadListener, ...]:
    """Allocate one loopback port per selected node.

    Ports already used by the core (mixed/API/DNS) are passed through *avoid*.
    A picker may return a duplicate or an invalid port; the allocator retries
    with a larger avoid set so a conflict automatically moves to another port.
    """
    ordered: list[str] = []
    seen: set[str] = set()
    for node in nodes:
        name = str(node).strip()
        if name and name not in seen:
            seen.add(name)
            ordered.append(name)
    if not ordered:
        return ()

    used = {int(port) for port in avoid if port}
    picker = port_picker or _default_picker
    listeners: list[DownloadListener] = []
    for index, node in enumerate(ordered, start=1):
        port = 0
        for _ in range(8):
            try:
                candidate = int(picker(set(used)))
            except OSError as exc:
                raise ConfigError(f"cannot reserve a listener port: {exc}") from exc
            if 1 <= candidate <= 65535 and candidate not in used:
                port = candidate
                break
            used.add(candidate)
        if not port:
            raise ConfigError("cannot reserve a free listener port for multi-node downloads")
        used.add(port)
        listeners.append(DownloadListener(name=f"ml-download-{index}", node=node, port=port))
    return tuple(listeners)
