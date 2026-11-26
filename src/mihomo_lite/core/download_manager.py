"""Qt adapter around the pure-Python download engine.

The engine never imports Qt and never talks to the controller. This class maps
the runtime session (mixed port plus one loopback listener per selected node)
into engine options, runs the engine on a background thread and republishes
progress through Qt signals.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from mihomo_lite.download.engine import DownloadEngine
from mihomo_lite.download.types import (
    DownloadOptions,
    DownloadResult,
    DownloadSnapshot,
    NodeRoute,
)
from mihomo_lite.models.app_state import ConnectionState

log = logging.getLogger(__name__)


class DownloadManager(QObject):
    started = Signal()
    progress = Signal(object)  # DownloadSnapshot
    node_state = Signal(object)  # tuple[NodeState, ...]
    warning = Signal(str)
    finished = Signal(object)  # DownloadResult
    failed = Signal(str)

    def __init__(self, settings, connection, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._connection = connection
        self._thread: threading.Thread | None = None
        self._cancel: threading.Event | None = None
        self._snapshot: DownloadSnapshot | None = None
        self._last_listener_ports: tuple[tuple[str, int], ...] = ()

        connection.state_changed.connect(self._on_connection_state)
        connection.session_changed.connect(self._on_session_changed)

    @property
    def active(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def snapshot(self) -> DownloadSnapshot | None:
        return self._snapshot

    def start(self, url: str, target: Path) -> bool:
        if self.active:
            self.warning.emit("A download is already running.")
            return False
        session = self._connection.session
        if not self._connection.is_connected or session is None:
            self.warning.emit("Connect first; downloads go through the local Mihomo proxy.")
            return False
        if not url.lower().startswith(("http://", "https://")):
            self.warning.emit("Enter an http:// or https:// URL.")
            return False
        target = Path(target)
        if not target.name:
            self.warning.emit("Choose where the file should be saved.")
            return False
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self.warning.emit(f"Cannot create the download folder: {exc}")
            return False

        settings = self._settings.current
        multithreaded = bool(settings.download_multithreaded)
        multi_node = bool(
            multithreaded and settings.download_multi_node and session.download_listeners
        )
        if settings.download_multi_node and not session.download_listeners:
            self.warning.emit(
                "Multi-node is enabled but this connection has no download listeners. "
                "Reconnect to apply the selected nodes; falling back to one node."
            )

        routes = (
            tuple(
                NodeRoute(name=listener.node, port=listener.port)
                for listener in session.download_listeners
            )
            if multi_node
            else ()
        )
        options = DownloadOptions(
            url=url,
            target=target,
            proxy_port=session.mixed_port,
            thread_count=int(settings.download_threads),
            multithreaded=multithreaded,
            multi_node=multi_node,
            node_routes=routes,
        )
        self._cancel = threading.Event()
        self._snapshot = None
        self._last_listener_ports = tuple(
            (listener.name, listener.port) for listener in session.download_listeners
        )
        self._thread = threading.Thread(
            target=self._run,
            args=(options, self._cancel),
            name="mihomo-lite-download",
            daemon=True,
        )
        self._thread.start()
        self.started.emit()
        return True

    def cancel(self) -> None:
        if self._cancel is not None:
            self._cancel.set()

    def _run(self, options: DownloadOptions, cancel: threading.Event) -> None:
        engine = DownloadEngine()

        def _on_snapshot(snapshot: DownloadSnapshot) -> None:
            self._snapshot = snapshot
            self.progress.emit(snapshot)
            if snapshot.nodes:
                self.node_state.emit(tuple(snapshot.nodes))

        try:
            result = engine.run(options, on_snapshot=_on_snapshot, cancel=cancel)
        except Exception as exc:  # noqa: BLE001 - report every engine failure to the UI
            log.exception("download failed")
            self.failed.emit(str(exc))
            self.finished.emit(
                DownloadResult(
                    target=options.target,
                    total=0,
                    downloaded=0,
                    ok=False,
                    error=str(exc),
                )
            )
            return
        if result.fallback_reason:
            self.warning.emit(result.fallback_reason)
        self.finished.emit(result)

    def _on_connection_state(self, state: ConnectionState) -> None:
        if self.active and state is not ConnectionState.CONNECTED:
            self.cancel()
            self.warning.emit("The connection changed; the download was cancelled.")

    def _on_session_changed(self, session: object) -> None:
        if not self.active:
            return
        listeners = getattr(session, "download_listeners", ())
        ports = tuple((listener.name, listener.port) for listener in listeners)
        if ports != self._last_listener_ports:
            self.cancel()
            self.warning.emit(
                "The download listener ports changed; the download was cancelled. Start it again."
            )
