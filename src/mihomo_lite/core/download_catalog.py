"""Read-only catalogue of nodes across every imported profile.

Multi-node downloads may span subscriptions/profiles, but only the active
profile is loaded by the core. The catalogue resolves the user's selection into
extra proxy definitions that the runtime generator appends to its deep copy.
Imported files are only read here.
"""

from __future__ import annotations

import copy
import logging
from dataclasses import dataclass
from typing import Any

from mihomo_lite.config.loader import load_yaml_file
from mihomo_lite.core.profile_manager import ProfileManager
from mihomo_lite.utils.exceptions import ConfigError

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class CatalogNode:
    key: str
    name: str
    profile_id: str
    profile_name: str
    proxy: dict[str, Any]
    conflict: bool = False
    conflict_with: tuple[str, ...] = ()


class DownloadCatalog:
    """Lazily scans profile files and resolves a cross-profile selection."""

    def __init__(self, profiles: ProfileManager) -> None:
        self._profiles = profiles
        self._nodes: list[CatalogNode] = []
        self._fingerprint: tuple[tuple[str, float], ...] = ()

    def invalidate(self) -> None:
        self._nodes = []
        self._fingerprint = ()

    def _current_fingerprint(self) -> tuple[tuple[str, float], ...]:
        return tuple(
            (profile.id, float(profile.updated_at or 0.0))
            for profile in self._profiles.profiles
        )

    def nodes(self, *, force: bool = False) -> list[CatalogNode]:
        fingerprint = self._current_fingerprint()
        if not force and self._nodes and fingerprint == self._fingerprint:
            return list(self._nodes)

        nodes: list[CatalogNode] = []
        by_name: dict[str, list[dict[str, Any]]] = {}
        for profile in self._profiles.profiles:
            path = self._profiles.profile_path(profile.id)
            if not path.exists():
                continue
            try:
                data = load_yaml_file(path)
            except Exception as exc:  # noqa: BLE001 - one bad profile must not hide the rest
                log.warning("cannot read nodes from profile %s: %s", profile.name, exc)
                continue
            proxies = data.get("proxies")
            if not isinstance(proxies, list):
                continue
            for proxy in proxies:
                if not isinstance(proxy, dict):
                    continue
                name = str(proxy.get("name") or "").strip()
                if not name:
                    continue
                entry = copy.deepcopy(proxy)
                nodes.append(
                    CatalogNode(
                        key=f"{profile.id}::{name}",
                        name=name,
                        profile_id=profile.id,
                        profile_name=profile.name,
                        proxy=entry,
                    )
                )
                by_name.setdefault(name, []).append(entry)

        duplicates = {
            name: tuple(
                sorted(
                    {
                        candidate.profile_name
                        for candidate in nodes
                        if candidate.name == name
                    }
                )
            )
            for name, definitions in by_name.items()
            if len({self._freeze(definition) for definition in definitions}) > 1
        }
        if duplicates:
            nodes = [
                CatalogNode(
                    key=node.key,
                    name=node.name,
                    profile_id=node.profile_id,
                    profile_name=node.profile_name,
                    proxy=node.proxy,
                    conflict=node.name in duplicates,
                    conflict_with=duplicates.get(node.name, ()),
                )
                for node in nodes
            ]

        nodes.sort(key=lambda item: (item.profile_name.lower(), item.name.lower()))
        self._nodes = nodes
        self._fingerprint = fingerprint
        return list(self._nodes)

    @staticmethod
    def _freeze(proxy: dict[str, Any]) -> str:
        import json

        return json.dumps(proxy, sort_keys=True, ensure_ascii=True, default=str)

    def by_key(self, key: str) -> CatalogNode | None:
        for node in self.nodes():
            if node.key == key:
                return node
        return None

    def resolve(
        self,
        selected_keys: list[str] | tuple[str, ...],
        active_data: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], list[str]]:
        """Return extra proxy definitions plus unique node names, in user order."""
        keys = [str(key) for key in selected_keys if str(key).strip()]
        if not keys:
            return [], []
        catalogue = {node.key: node for node in self.nodes()}
        active_proxies = active_data.get("proxies")
        active_by_name = {
            str(proxy.get("name")): proxy
            for proxy in (active_proxies if isinstance(active_proxies, list) else [])
            if isinstance(proxy, dict) and proxy.get("name")
        }

        chosen: list[CatalogNode] = []
        for key in keys:
            node = catalogue.get(key)
            if node is None:
                raise ConfigError(
                    "a selected download node is no longer available; reopen the Downloads page"
                )
            if node.conflict:
                raise ConfigError(
                    f"node '{node.name}' is defined differently in several profiles; "
                    "rename one definition before selecting it"
                )
            chosen.append(node)

        extras: list[dict[str, Any]] = []
        extra_by_name: dict[str, dict[str, Any]] = {}
        names: list[str] = []
        for node in chosen:
            if node.name in names:
                continue
            names.append(node.name)
            active = active_by_name.get(node.name)
            if active is not None:
                if active != node.proxy:
                    raise ConfigError(
                        f"node '{node.name}' differs from the active profile; "
                        "rename one definition before selecting it"
                    )
                continue
            existing = extra_by_name.get(node.name)
            if existing is not None:
                if existing != node.proxy:
                    raise ConfigError(
                        f"node '{node.name}' is defined differently in several profiles"
                    )
                continue
            copied = copy.deepcopy(node.proxy)
            extras.append(copied)
            extra_by_name[node.name] = copied
        return extras, names
