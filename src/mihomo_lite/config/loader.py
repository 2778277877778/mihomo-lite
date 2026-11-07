"""YAML loading with bounded size and readable error messages."""

from __future__ import annotations

import io
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


def parse_yaml(text: str, *, source: str = "profile") -> dict[str, Any]:
    """Parse YAML text and require a mapping at the top level."""
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
    if not isinstance(data, dict):
        raise ConfigError(f"{source} must be a YAML mapping, got {type(data).__name__}")
    return data


def load_yaml_file(path: Path) -> dict[str, Any]:
    return parse_yaml(read_profile_text(path), source=path.name)


def load_yaml_text(text: str, *, source: str = "subscription") -> dict[str, Any]:
    text = text.strip()
    if not text:
        raise ConfigError(f"{source} is empty")
    if "<html" in text[:200].lower():
        raise ConfigError(
            f"{source} returned HTML instead of YAML - the link may be expired or require a login"
        )
    return parse_yaml(text, source=source)
