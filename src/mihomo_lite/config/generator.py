"""Turn an imported profile into a safe runtime configuration.

The original profile is never modified: every override happens on a deep copy
that is written to runtime/generated.yaml.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from mihomo_lite.config.defaults import MANAGED_KEYS
from mihomo_lite.utils.exceptions import ConfigError
from mihomo_lite.utils.fs import atomic_write_text


@dataclass
class GeneratedConfig:
    data: dict[str, Any]
    notes: list[str] = field(default_factory=list)

    def to_yaml(self) -> str:
        return yaml.safe_dump(self.data, allow_unicode=True, sort_keys=False, width=120)


def _local_dns(dns: Any) -> Any:
    if not isinstance(dns, dict):
        return dns
    listen = str(dns.get("listen", ""))
    if listen and not listen.startswith(("127.", "localhost", "[::1]", "::1")):
        dns = dict(dns)
        dns["listen"] = "127.0.0.1:0"
    return dns


def generate_runtime_config(
    profile: dict[str, Any],
    *,
    mixed_port: int,
    api_port: int,
    secret: str,
    log_level: str = "info",
    system_proxy: bool = True,
) -> GeneratedConfig:
    """Return a hardened copy of *profile* ready for the core to load."""
    if not isinstance(profile, dict):
        raise ConfigError("profile must be a mapping")
    if not secret:
        raise ConfigError("an API secret is required")
    if not (1 <= api_port <= 65535 and 1 <= mixed_port <= 65535):
        raise ConfigError("ports must be between 1 and 65535")

    data = copy.deepcopy(profile)
    notes: list[str] = []

    for key in ("external-controller-tls", "external-controller-unix", "external-controller-pipe"):
        if key in data:
            data.pop(key)
            notes.append(f"removed '{key}' (only the local REST endpoint is exposed)")

    data["external-controller"] = f"127.0.0.1:{api_port}"
    data["secret"] = secret
    data["bind-address"] = "127.0.0.1"
    data["allow-lan"] = False
    data["mixed-port"] = mixed_port
    data["port"] = 0
    data["socks-port"] = 0
    data["redir-port"] = 0
    data["tproxy-port"] = 0
    data["log-level"] = log_level.lower()
    data["mode"] = str(data.get("mode", "rule")).lower()
    data["ipv6"] = bool(data.get("ipv6", False))

    tun = data.get("tun")
    if isinstance(tun, dict) and tun.get("enable"):
        notes.append("TUN was requested by the profile but is disabled in this version")
    data["tun"] = {"enable": False}

    if data.get("listeners"):
        notes.append("custom listeners were removed; only the local mixed port is exposed")
    data.pop("listeners", None)

    profile_section = data.get("profile")
    profile_section = dict(profile_section) if isinstance(profile_section, dict) else {}
    profile_section["store-selected"] = True
    profile_section.setdefault("store-fake-ip", True)
    data["profile"] = profile_section

    if "dns" in data:
        data["dns"] = _local_dns(data["dns"])

    if system_proxy:
        notes.append(f"system proxy target: 127.0.0.1:{mixed_port}")

    for key in MANAGED_KEYS:
        if key not in data:
            notes.append(f"added '{key}'")
    return GeneratedConfig(data=data, notes=notes)


def write_runtime_config(path: Path, generated: GeneratedConfig) -> Path:
    text = generated.to_yaml()
    if "secret:" not in text:
        raise ConfigError("refusing to write a runtime config without a secret")
    atomic_write_text(path, text)
    return path
