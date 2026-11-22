"""Semantic validation for imported Mihomo profiles.

The validator is intentionally conservative: anything that would make the core
fail to start is an error, anything the app silently overrides is a warning.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from mihomo_lite.config.rules import SEVERITY_ERROR, analyze_rules
from mihomo_lite.utils.exceptions import ConfigError

_PROXY_GROUP_TYPES = {
    "select",
    "urltest",
    "fallback",
    "load-balance",
    "relay",
}


@dataclass
class ValidationResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def add_error(self, message: str) -> None:
        self.errors.append(message)

    def add_warning(self, message: str) -> None:
        self.warnings.append(message)

    def summary(self) -> str:
        if self.ok:
            if self.warnings:
                return f"Valid configuration with {len(self.warnings)} warning(s)."
            return "Configuration looks good."
        return f"{len(self.errors)} error(s) found."


def validate_config(data: dict[str, Any]) -> ValidationResult:
    result = ValidationResult()

    proxies = data.get("proxies")
    providers = data.get("proxy-providers")
    if proxies is None and providers is None:
        result.add_error("missing 'proxies' or 'proxy-providers' section")
    elif proxies is not None and not isinstance(proxies, list):
        result.add_error("'proxies' must be a list")
    elif isinstance(proxies, list) and proxies:
        _validate_proxies(proxies, result)

    if providers is not None and not isinstance(providers, dict):
        result.add_error("'proxy-providers' must be a mapping")

    _validate_groups(data, result)
    _validate_rules(data, result)
    _validate_ports(data, result)
    _validate_safety(data, result)
    return result


def _validate_proxies(proxies: list[Any], result: ValidationResult) -> None:
    seen: set[str] = set()
    for index, proxy in enumerate(proxies):
        if not isinstance(proxy, dict):
            result.add_error(f"proxies[{index}] must be a mapping")
            continue
        name = proxy.get("name")
        if not name or not isinstance(name, str):
            result.add_error(f"proxies[{index}] is missing a 'name'")
            continue
        if name in seen:
            result.add_error(f"duplicate proxy name: {name}")
        seen.add(name)
        if not proxy.get("type"):
            result.add_error(f"proxy '{name}' is missing a 'type'")


def _validate_groups(data: dict[str, Any], result: ValidationResult) -> None:
    groups = data.get("proxy-groups")
    if groups is None:
        return
    if not isinstance(groups, list):
        result.add_error("'proxy-groups' must be a list")
        return

    proxy_names = {
        proxy.get("name")
        for proxy in data.get("proxies") or []
        if isinstance(proxy, dict) and proxy.get("name")
    }
    group_names = {
        group.get("name")
        for group in groups
        if isinstance(group, dict) and group.get("name")
    }
    provider_names = set((data.get("proxy-providers") or {}).keys())

    for index, group in enumerate(groups):
        if not isinstance(group, dict):
            result.add_error(f"proxy-groups[{index}] must be a mapping")
            continue
        name = group.get("name")
        if not name:
            result.add_error(f"proxy-groups[{index}] is missing a 'name'")
            continue
        group_type = str(group.get("type", "")).lower()
        if not group_type:
            result.add_error(f"proxy group '{name}' is missing a 'type'")
            continue
        if group_type not in _PROXY_GROUP_TYPES:
            result.add_warning(f"proxy group '{name}' uses an unusual type: {group_type}")

        members = group.get("proxies") or []
        if not isinstance(members, list):
            result.add_error(f"proxy group '{name}' has a non-list 'proxies' field")
            continue
        if group_type != "relay" and not members and not group.get("use"):
            result.add_error(f"proxy group '{name}' has no proxies")
        for member in members:
            if member in ("DIRECT", "REJECT", group_names):
                continue
            if member not in proxy_names and not _is_known_provider(member, provider_names):
                result.add_warning(f"proxy group '{name}' references unknown proxy '{member}'")


def _is_known_provider(name: str, providers: set[str]) -> bool:
    return name in providers


def _validate_rules(data: dict[str, Any], result: ValidationResult) -> None:
    analysis = analyze_rules(data)
    for issue in analysis.issues:
        if issue.severity == SEVERITY_ERROR:
            result.add_error(issue.as_text())
        else:
            result.add_warning(issue.as_text())


def _validate_ports(data: dict[str, Any], result: ValidationResult) -> None:
    for key in ("mixed-port", "port", "socks-port", "redir-port", "tproxy-port"):
        if key not in data:
            continue
        value = data[key]
        if not isinstance(value, int) or isinstance(value, bool):
            result.add_error(f"'{key}' must be an integer port number")
        elif not (0 <= value <= 65535):
            result.add_error(f"'{key}' is out of range: {value}")


def _validate_safety(data: dict[str, Any], result: ValidationResult) -> None:
    controller = data.get("external-controller")
    if controller:
        result.add_warning(
            "the profile's 'external-controller' is replaced by a local, "
            "randomly authenticated endpoint"
        )
    if data.get("allow-lan"):
        result.add_warning("'allow-lan' is forced off so the proxy stays on localhost")

    tun = data.get("tun")
    if isinstance(tun, dict) and tun.get("enable"):
        result.add_warning("TUN mode is not supported in this version and will be disabled")

    listeners = data.get("listeners")
    if listeners:
        result.add_warning(
            f"{len(listeners)} custom listener(s) are disabled; only the local mixed port is exposed"
        )

    dns = data.get("dns")
    if isinstance(dns, dict):
        listen = str(dns.get("listen", ""))
        if listen and not listen.startswith(("127.", "localhost", "[::1]", "::1")):
            result.add_warning(f"DNS listen address '{listen}' is replaced by a localhost bind")


def require_valid(data: dict[str, Any]) -> ValidationResult:
    """Raise ConfigError when the profile cannot be used at all."""
    result = validate_config(data)
    if not result.ok:
        raise ConfigError("; ".join(result.errors))
    return result
