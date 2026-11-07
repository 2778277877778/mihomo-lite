"""Proxy groups and nodes as reported by the Mihomo REST API."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

GROUP_TYPES = {"Selector", "URLTest", "Fallback", "LoadBalance", "Relay"}


@dataclass(frozen=True)
class ProxyNode:
    name: str
    type: str = ""
    delay_ms: int | None = None
    udp: bool = False
    alive: bool = True

    @property
    def delay_label(self) -> str:
        if self.delay_ms is None:
            return "-"
        if self.delay_ms == 0:
            return "timeout"
        return f"{self.delay_ms} ms"


@dataclass
class ProxyGroup:
    name: str
    type: str
    now: str = ""
    members: list[str] = field(default_factory=list)
    delays: dict[str, int] = field(default_factory=dict)

    @property
    def is_selector(self) -> bool:
        return self.type == "Selector"

    def delay_of(self, name: str) -> int | None:
        return self.delays.get(name)


def parse_proxies(payload: dict[str, Any]) -> tuple[list[ProxyGroup], dict[str, ProxyNode]]:
    """Split the /proxies response into groups, nodes and group selection state."""
    raw = payload.get("proxies") if isinstance(payload, dict) else None
    if not isinstance(raw, dict):
        return [], {}

    nodes: dict[str, ProxyNode] = {}
    groups: list[ProxyGroup] = []

    for name, entry in raw.items():
        if not isinstance(entry, dict):
            continue
        entry_type = str(entry.get("type", ""))
        if entry_type in GROUP_TYPES:
            history = entry.get("history") or []
            delays: dict[str, int] = {}
            groups.append(
                ProxyGroup(
                    name=name,
                    type=entry_type,
                    now=str(entry.get("now", "")),
                    members=[str(m) for m in entry.get("all") or []],
                    delays=delays,
                )
            )
            continue
        if entry_type in {"Direct", "Reject", "RejectDrop", "Compatible", "Pass"}:
            continue
        history = entry.get("history") or []
        delay: int | None = None
        if history and isinstance(history[-1], dict):
            try:
                delay = int(history[-1].get("delay", 0))
            except (TypeError, ValueError):
                delay = None
        nodes[name] = ProxyNode(
            name=name,
            type=entry_type,
            delay_ms=delay,
            udp=bool(entry.get("udp", False)),
            alive=bool(entry.get("alive", True)),
        )

    groups.sort(key=lambda g: (g.type != "Selector", g.name.lower()))
    return groups, nodes
