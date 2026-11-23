"""Proxy groups, node selection and latency tests."""

from __future__ import annotations

import logging
from collections.abc import Callable

from PySide6.QtCore import QObject, Signal

from mihomo_lite.mihomo.api import MihomoAPI
from mihomo_lite.models.proxy import ProxyGroup, ProxyNode, parse_proxies
from mihomo_lite.utils.tasks import TaskRunner

DEFAULT_DELAY_URL = "http://www.gstatic.com/generate_204"

log = logging.getLogger(__name__)


class ProxyManager(QObject):
    groups_updated = Signal(object, object)  # list[ProxyGroup], dict[str, ProxyNode]
    delays_updated = Signal(object)  # dict[str, int]
    selection_changed = Signal(str, str)
    failed = Signal(str)
    node_stats = Signal(object)  # {name: {"delay": ms, "jitter": ms}}
    mode_changed = Signal(str)

    def __init__(
        self,
        api_provider: Callable[[], MihomoAPI | None],
        runner: TaskRunner,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._api_provider = api_provider
        self._runner = runner
        self._groups: list[ProxyGroup] = []
        self._nodes: dict[str, ProxyNode] = {}
        self._history: dict[str, list[int]] = {}
        self._stats: dict[str, dict[str, int]] = {}
        self._mode = ""

    @property
    def groups(self) -> list[ProxyGroup]:
        return list(self._groups)

    @property
    def nodes(self) -> dict[str, ProxyNode]:
        return dict(self._nodes)

    def refresh(self) -> None:
        api = self._api_provider()
        if api is None:
            return
        self._runner.submit(
            api.proxies,
            on_success=self._on_proxies,
            on_error=self.failed.emit,
        )

    def _on_proxies(self, payload: object) -> None:
        if not isinstance(payload, dict):
            return
        groups, nodes = parse_proxies(payload)
        self._groups = groups
        self._nodes = nodes
        log.info("loaded %s proxy groups and %s nodes", len(groups), len(nodes))
        self.groups_updated.emit(groups, nodes)

    def _record_delays(self, delays: dict[str, int]) -> None:
        for name, delay in delays.items():
            if delay <= 0:
                continue
            samples = self._history.setdefault(name, [])
            samples.append(delay)
            del samples[:-5]
            jitter = max(samples) - min(samples) if len(samples) > 1 else 0
            self._stats[name] = {"delay": delay, "jitter": jitter}

    @property
    def stats(self) -> dict[str, dict[str, int]]:
        return dict(self._stats)

    @property
    def mode(self) -> str:
        return self._mode

    def load_config(self) -> None:
        api = self._api_provider()
        if api is None:
            return

        def _ok(result: object) -> None:
            if isinstance(result, dict) and result.get("mode"):
                self._mode = str(result["mode"]).lower()
                self.mode_changed.emit(self._mode)

        self._runner.submit(api.configs, on_success=_ok, on_error=self.failed.emit)

    def set_mode(self, mode: str) -> None:
        api = self._api_provider()
        if api is None:
            return

        def _ok(_result: object) -> None:
            self._mode = mode
            self.mode_changed.emit(mode)

        self._runner.submit(
            api.set_mode, args=(mode,), on_success=_ok, on_error=self.failed.emit
        )

    def test_node_delay(self, name: str, url: str = DEFAULT_DELAY_URL, *, timeout_ms: int = 5000) -> None:
        api = self._api_provider()
        if api is None or not name:
            return

        def _ok(delay: object) -> None:
            try:
                value = int(delay)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                return
            if value > 0:
                self._record_delays({name: value})
                self.node_stats.emit(dict(self._stats))

        self._runner.submit(
            api.proxy_delay,
            args=(name, url),
            kwargs={"timeout_ms": timeout_ms},
            on_success=_ok,
            on_error=lambda _message: None,
        )

    def select(self, group: str, name: str) -> None:
        api = self._api_provider()
        if api is None:
            return

        def _ok(_: object) -> None:
            self.selection_changed.emit(group, name)
            self.refresh()

        self._runner.submit(
            api.select_proxy,
            args=(group, name),
            on_success=_ok,
            on_error=self.failed.emit,
        )

    def test_group_delay(
        self, group: str, url: str = DEFAULT_DELAY_URL, timeout_ms: int = 5000
    ) -> None:
        api = self._api_provider()
        if api is None:
            return

        def _ok(result: object) -> None:
            if isinstance(result, dict):
                self.delays_updated.emit(result)
                self._record_delays(result)
                for existing in self._groups:
                    if existing.name == group:
                        existing.delays.update(result)
                self.groups_updated.emit(self._groups, self._nodes)
                self.node_stats.emit(dict(self._stats))

        self._runner.submit(
            api.group_delay,
            args=(group, url),
            kwargs={"timeout_ms": timeout_ms},
            on_success=_ok,
            on_error=self.failed.emit,
        )
