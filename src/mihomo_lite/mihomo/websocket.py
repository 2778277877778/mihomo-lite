"""Traffic WebSocket client running in its own thread with its own asyncio loop.

Keeping asyncio out of the Qt event loop avoids the qasync dependency while
still giving us real-time traffic with automatic reconnects.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from typing import Any

import websockets
from PySide6.QtCore import QThread, Signal

log = logging.getLogger(__name__)


class TrafficSocket(QThread):
    traffic = Signal(object)  # decoded {"up": int, "down": int, ...}
    connected = Signal()
    disconnected = Signal(str)

    def __init__(self, port: int, secret: str, parent=None) -> None:
        super().__init__(parent)
        self._port = port
        self._secret = secret
        self._stop = threading.Event()
        self._reconnect_delay = 1.0

    @property
    def url(self) -> str:
        return f"ws://127.0.0.1:{self._port}/traffic"

    def stop(self) -> None:
        self._stop.set()

    def stop_and_wait(self, timeout_ms: int = 4000) -> None:
        self._stop.set()
        if self.isRunning():
            self.wait(timeout_ms)

    def run(self) -> None:
        try:
            asyncio.run(self._loop())
        except Exception as exc:  # noqa: BLE001 - thread must not raise
            log.error("traffic socket stopped unexpectedly: %s", exc)

    async def _loop(self) -> None:
        headers = {"Authorization": f"Bearer {self._secret}"}
        while not self._stop.is_set():
            try:
                async with websockets.connect(
                    self.url,
                    additional_headers=headers,
                    open_timeout=5,
                    ping_interval=20,
                    close_timeout=2,
                    max_size=1 << 20,
                ) as socket:
                    self._reconnect_delay = 1.0
                    self.connected.emit()
                    await self._pump(socket)
            except asyncio.CancelledError:
                break
            except Exception as exc:  # noqa: BLE001 - reconnect on any failure
                if not self._stop.is_set():
                    log.debug("traffic socket disconnected: %s", exc)
                    self.disconnected.emit(str(exc))
            if self._stop.is_set():
                break
            await asyncio.sleep(self._reconnect_delay)
            self._reconnect_delay = min(self._reconnect_delay * 2, 10.0)

    async def _pump(self, socket: Any) -> None:
        while not self._stop.is_set():
            try:
                message = await asyncio.wait_for(socket.recv(), timeout=1.0)
            except TimeoutError:
                continue
            if self._stop.is_set():
                return
            if isinstance(message, bytes):
                message = message.decode("utf-8", errors="replace")
            try:
                payload = json.loads(message)
            except ValueError:
                continue
            if isinstance(payload, dict):
                self.traffic.emit(payload)
