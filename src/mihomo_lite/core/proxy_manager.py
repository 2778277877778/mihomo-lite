"""Proxy groups, node selection and latency tests."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject, Signal

from mihomo_lite.mihomo.api import MihomoAPI
from mihomo_lite.models.proxy import ProxyGroup, ProxyNode, parse_proxies
from mihomo_lite.utils.tasks import TaskRunner

DEFAULT_DELAY_URL = "http://www.gstatic.com/generate_204"


class ProxyManager(QObject):
    groups_updated = Signal(object, object)  # list[ProxyGroup], dict[str, ProxyNode]
    delays_updated = Signal(object)  # dict[str, int]
    selection_changed = Signal(str, str)
    failed = Signal(str)

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
        self.groups_updated.emit(groups, nodes)

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
                for existing in self._groups:
                    if existing.name == group:
                        existing.delays.update(result)
                self.groups_updated.emit(self._groups, self._nodes)

        self._runner.submit(
            api.group_delay,
            args=(group, url),
            kwargs={"timeout_ms": timeout_ms},
            on_success=_ok,
            on_error=self.failed.emit,
        )
