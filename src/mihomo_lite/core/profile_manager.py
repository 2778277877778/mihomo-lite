"""Import, list, update and remove configuration profiles.

Layout on disk (profiles are never edited in place by the app):

    profiles/<id>/original.yaml   current bytes (what the user imported)
    profiles/<id>/previous.yaml   last known good bytes before an update
    profiles/index.json           metadata + active profile id
"""

from __future__ import annotations

import logging
import time
import uuid
from pathlib import Path

import httpx
from PySide6.QtCore import QObject, Signal

from mihomo_lite.config.defaults import ALLOWED_PROFILE_SUFFIXES, MAX_PROFILE_BYTES
from mihomo_lite.config.loader import (
    load_yaml_file,
    load_yaml_text,
    looks_like_link_subscription,
    parse_yaml,
)
from mihomo_lite.config.validator import validate_config
from mihomo_lite.models.profile import Profile, ProfileKind
from mihomo_lite.system.paths import AppPaths
from mihomo_lite.utils.exceptions import ConfigError, MihomoLiteError
from mihomo_lite.utils.fs import atomic_write_text, read_json
from mihomo_lite.utils.logger import redact_url

log = logging.getLogger(__name__)

# Providers decide the payload format from the User-Agent: Clash-style agents get
# YAML, everything else often gets a base64 link list. Try the common ones first.
_USER_AGENTS = (
    "clash-verge/v2.0.0",
    "ClashMetaForAndroid/2.11.1.Meta",
    "mihomo/1.19.33",
    "MihomoLite/0.3.0 (+https://github.com/2778277877778/mihomo-lite)",
)


def _download_text(url: str, user_agent: str, timeout: float) -> str:
    chunks: list[bytes] = []
    try:
        with httpx.Client(
            follow_redirects=True,
            timeout=timeout,
            headers={"User-Agent": user_agent},
            trust_env=False,
        ) as client, client.stream("GET", url) as response:
            if response.status_code >= 400:
                raise ConfigError(f"subscription returned HTTP {response.status_code}")
            total = 0
            for chunk in response.iter_bytes():
                total += len(chunk)
                if total > MAX_PROFILE_BYTES:
                    raise ConfigError("subscription is larger than the 16 MB limit")
                chunks.append(chunk)
    except httpx.HTTPError as exc:
        raise ConfigError(f"cannot download the subscription: {redact_url(str(exc))}") from exc

    raw = b"".join(chunks)
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ConfigError("subscription is not valid UTF-8 text")


def fetch_subscription(url: str, *, timeout: float = 25.0) -> str:
    """Download a subscription, asking for Clash YAML with Clash-style agents."""
    if not url.lower().startswith(("http://", "https://")):
        raise ConfigError("subscription URL must start with http:// or https://")

    last_error: ConfigError | None = None
    for user_agent in _USER_AGENTS:
        try:
            text = _download_text(url, user_agent, timeout)
        except ConfigError as exc:
            last_error = exc
            continue

        stripped = text.strip()
        if looks_like_link_subscription(stripped):
            last_error = ConfigError(
                "the provider returned a v2ray/ss link list for every Clash User-Agent. "
                "Use the Clash subscription address from your provider "
                "(often with &flag=clash or a /clash path)."
            )
            continue
        if stripped.startswith("<"):
            last_error = ConfigError(
                "the link returned HTML (expired link, login wall or Cloudflare challenge)"
            )
            continue
        return text

    if last_error is not None:
        raise ConfigError(f"{url.split('/')[2]}: {last_error}")
    raise ConfigError("cannot download the subscription")


class ProfileManager(QObject):
    profiles_changed = Signal()
    active_changed = Signal(object)

    def __init__(self, paths: AppPaths, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._paths = paths
        self._profiles: list[Profile] = []
        self._active_id: str = ""
        self.load()

    # -- persistence -------------------------------------------------------
    def load(self) -> None:
        raw = read_json(self._paths.profiles_index, default={}) or {}
        profiles = raw.get("profiles") if isinstance(raw, dict) else None
        self._profiles = []
        if isinstance(profiles, list):
            for entry in profiles:
                if isinstance(entry, dict):
                    profile = Profile.from_dict(entry)
                    if profile.id and self.profile_path(profile.id).exists():
                        self._profiles.append(profile)
        active = raw.get("active") if isinstance(raw, dict) else ""
        self._active_id = str(active or "")
        if self._active_id and not any(p.id == self._active_id for p in self._profiles):
            self._active_id = ""

    def _save_index(self) -> None:
        payload = {
            "active": self._active_id,
            "profiles": [profile.to_dict() for profile in self._profiles],
        }
        try:
            from mihomo_lite.utils.fs import atomic_write_json

            atomic_write_json(self._paths.profiles_index, payload)
        except OSError as exc:
            log.error("cannot save profile index: %s", exc)

    # -- accessors ---------------------------------------------------------
    @property
    def profiles(self) -> list[Profile]:
        return list(self._profiles)

    @property
    def active_id(self) -> str:
        return self._active_id

    def get(self, profile_id: str) -> Profile | None:
        for profile in self._profiles:
            if profile.id == profile_id:
                return profile
        return None

    def active_profile(self) -> Profile | None:
        return self.get(self._active_id) if self._active_id else None

    def profile_dir(self, profile_id: str) -> Path:
        return self._paths.profiles / profile_id

    def profile_path(self, profile_id: str) -> Path:
        return self.profile_dir(profile_id) / "original.yaml"

    def previous_path(self, profile_id: str) -> Path:
        return self.profile_dir(profile_id) / "previous.yaml"

    # -- imports -----------------------------------------------------------
    def import_file(self, source: Path, name: str | None = None) -> Profile:
        if not source.exists():
            raise ConfigError(f"file not found: {source}")
        if source.suffix.lower() not in ALLOWED_PROFILE_SUFFIXES:
            raise ConfigError("only .yaml and .yml profiles are supported")
        text = source.read_text(encoding="utf-8-sig")
        profile = self.import_text(text, name=name or source.stem, kind=ProfileKind.LOCAL)
        return profile

    def import_text(
        self,
        text: str,
        *,
        name: str,
        kind: ProfileKind = ProfileKind.LOCAL,
        url: str = "",
    ) -> Profile:
        data = load_yaml_text(text, source=name)
        result = validate_config(data)
        if not result.ok:
            raise ConfigError("; ".join(result.errors))

        profile_id = uuid.uuid4().hex[:12]
        directory = self.profile_dir(profile_id)
        directory.mkdir(parents=True, exist_ok=True)
        atomic_write_text(self.profile_path(profile_id), text)

        profile = Profile(
            id=profile_id,
            name=name.strip() or "Unnamed profile",
            kind=kind,
            url=url,
            updated_at=time.time(),
            size=len(text.encode("utf-8")),
            proxy_count=len(data.get("proxies") or []),
            group_count=len(data.get("proxy-groups") or []),
            rule_count=len(data.get("rules") or []),
            note="; ".join(result.warnings[:3]),
        )
        self._profiles.append(profile)
        self._save_index()
        self.profiles_changed.emit()

        if not self._active_id:
            self.set_active(profile_id)
        log.info("imported profile %s (%s)", profile.name, profile.kind.value)
        return profile

    def import_subscription(self, url: str, name: str | None = None) -> Profile:
        text = fetch_subscription(url)
        label = name or url.split("//", 1)[-1].split("/", 1)[0]
        return self.import_text(text, name=label, kind=ProfileKind.SUBSCRIPTION, url=url)

    # -- updates -----------------------------------------------------------
    def refresh(self, profile_id: str, fetcher=fetch_subscription) -> Profile:
        """Download new bytes, validate, back up the old ones, then replace."""
        profile = self.get(profile_id)
        if profile is None:
            raise ConfigError("profile not found")
        if profile.kind is not ProfileKind.SUBSCRIPTION or not profile.url:
            raise ConfigError("only subscription profiles can be refreshed")

        text = fetcher(profile.url)
        data = load_yaml_text(text, source=profile.name)
        result = validate_config(data)
        if not result.ok:
            raise ConfigError("new subscription is invalid: " + "; ".join(result.errors))

        current = self.profile_path(profile_id)
        if current.exists():
            atomic_write_text(self.previous_path(profile_id), current.read_text(encoding="utf-8"))
        atomic_write_text(current, text)

        profile.updated_at = time.time()
        profile.size = len(text.encode("utf-8"))
        profile.proxy_count = len(data.get("proxies") or [])
        profile.group_count = len(data.get("proxy-groups") or [])
        profile.rule_count = len(data.get("rules") or [])
        profile.note = "; ".join(result.warnings[:3])
        self._save_index()
        self.profiles_changed.emit()
        log.info("refreshed profile %s", profile.name)
        return profile

    # -- lifecycle ---------------------------------------------------------
    def set_active(self, profile_id: str) -> None:
        if self.get(profile_id) is None:
            raise ConfigError("profile not found")
        self._active_id = profile_id
        self._save_index()
        self.active_changed.emit(self.active_profile())

    def delete(self, profile_id: str) -> None:
        profile = self.get(profile_id)
        if profile is None:
            return
        import shutil

        shutil.rmtree(self.profile_dir(profile_id), ignore_errors=True)
        self._profiles = [p for p in self._profiles if p.id != profile_id]
        if self._active_id == profile_id:
            self._active_id = self._profiles[0].id if self._profiles else ""
        self._save_index()
        self.profiles_changed.emit()
        if self._active_id:
            self.active_changed.emit(self.active_profile())

    def load_active_config(self) -> dict:
        profile = self.active_profile()
        if profile is None:
            raise ConfigError("no profile is selected")
        return load_yaml_file(self.profile_path(profile.id))

    def validate_active(self) -> tuple[bool, str]:
        try:
            data = self.load_active_config()
        except ConfigError as exc:
            return False, str(exc)
        result = validate_config(data)
        return result.ok, result.summary()


def count_entries(text: str) -> tuple[int, int]:
    """Best-effort counts for UI previews (never raises)."""
    try:
        data = parse_yaml(text)
    except MihomoLiteError:
        return 0, 0
    return len(data.get("proxies") or []), len(data.get("proxy-groups") or [])
