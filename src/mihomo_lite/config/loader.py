"""YAML loading with bounded size and readable error messages."""

from __future__ import annotations

import base64
import io
import re
from pathlib import Path
from typing import Any

import yaml

from mihomo_lite.config.defaults import ALLOWED_PROFILE_SUFFIXES, MAX_PROFILE_BYTES
from mihomo_lite.utils.exceptions import ConfigError


def read_profile_text(path: Path) -> str:
    """Read a profile file, rejecting oversized or non-YAML inputs."""
    if not path.exists():
        raise ConfigError(f"file not found: {path}")
    if path.suffix.lower() not in ALLOWED_PROFILE_SUFFIXES:
        raise ConfigError("only .yaml and .yml profiles are supported")
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise ConfigError(f"cannot read {path.name}: {exc}") from exc
    if size > MAX_PROFILE_BYTES:
        raise ConfigError(
            f"profile is too large ({size / 1024 / 1024:.1f} MB, limit "
            f"{MAX_PROFILE_BYTES // 1024 // 1024} MB)"
        )
    try:
        return path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ConfigError("profile is not valid UTF-8 text") from exc
    except OSError as exc:
        raise ConfigError(f"cannot read {path.name}: {exc}") from exc


def _parse_any(text: str, *, source: str) -> Any:
    """Parse YAML without enforcing a top-level mapping."""
    if len(text.encode("utf-8", errors="ignore")) > MAX_PROFILE_BYTES:
        raise ConfigError(f"{source} is too large to import")
    try:
        data = yaml.safe_load(io.StringIO(text))
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        where = f" (line {mark.line + 1}, column {mark.column + 1})" if mark else ""
        problem = getattr(exc, "problem", None) or str(exc)
        raise ConfigError(f"{source} is not valid YAML{where}: {problem}") from exc
    if data is None:
        raise ConfigError(f"{source} is empty")
    return data


def parse_yaml(text: str, *, source: str = "profile") -> dict[str, Any]:
    """Parse YAML text and require a mapping at the top level."""
    data = _parse_any(text, source=source)
    if not isinstance(data, dict):
        raise ConfigError(f"{source} must be a YAML mapping, got {type(data).__name__}")
    return data


def load_yaml_file(path: Path) -> dict[str, Any]:
    return parse_yaml(read_profile_text(path), source=path.name)


_PROXY_URI = re.compile(
    r"^(ss|ssr|vmess|vless|trojan|hysteria2?|tuic|wireguard|socks|http)://", re.IGNORECASE | re.MULTILINE
)


def _looks_like_links(text: str) -> bool:
    return bool(_PROXY_URI.search(text[:4000]))


def _links_error(source: str) -> ConfigError:
    return ConfigError(
        f"{source} is a subscription of proxy links (v2ray/ss/...), not a Clash/Mihomo "
        "profile. Use the converted Clash subscription URL from your provider "
        "(often with &flag=clash or a /clash path)."
    )


def _try_base64(text: str) -> str | None:
    compact = "".join(text.split())
    if len(compact) < 24:
        return None
    if not re.fullmatch(r"[A-Za-z0-9+/=_-]+", compact):
        return None
    normalized = compact.replace("-", "+").replace("_", "/")
    normalized += "=" * (-len(normalized) % 4)
    try:
        raw = base64.b64decode(normalized, validate=False)
        return raw.decode("utf-8-sig")
    except (ValueError, UnicodeDecodeError):
        return None


def looks_like_link_subscription(text: str) -> bool:
    """True when the payload is a v2ray/ss link list (raw or base64 wrapped)."""
    stripped = text.strip()
    if _looks_like_links(stripped):
        return True
    decoded = _try_base64(stripped)
    return bool(decoded and _looks_like_links(decoded))


def load_yaml_text(text: str, *, source: str = "subscription") -> dict[str, Any]:
    text = text.strip()
    if not text:
        raise ConfigError(f"{source} is empty")
    if text[:1] == "<" or "<html" in text[:200].lower():
        raise ConfigError(
            f"{source} returned HTML instead of YAML - the link may be expired, "
            "require a login, or need a different User-Agent"
        )
    if _looks_like_links(text):
        raise _links_error(source)

    data = _parse_any(text, source=source)
    if isinstance(data, str):
        # Many providers wrap the profile in base64; the decoded value is still
        # valid YAML, so YAML parses it as a plain scalar.
        decoded = _try_base64(data)
        if decoded is None:
            raise ConfigError(
                f"{source} is not a Clash/Mihomo profile (YAML mapping expected)"
            )
        if _looks_like_links(decoded):
            raise _links_error(source)
        decoded_data = _parse_any(decoded, source=source)
        if not isinstance(decoded_data, dict):
            raise ConfigError(f"{source} does not contain a Clash/Mihomo profile")
        return decoded_data
    if not isinstance(data, dict):
        raise ConfigError(f"{source} must be a YAML mapping, got {type(data).__name__}")
    return data
