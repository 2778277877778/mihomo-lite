"""Real-time traffic figures derived from the core WebSocket stream."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QObject, Signal

from mihomo_lite.mihomo.websocket import TrafficSocket


@dataclass(frozen=True)
class TrafficSample:
    up: int = 0
    down: int = 0
    up_total: int = 0
    down_total: int = 0


def human_bytes(value: float) -> str:
    units = ("B", "KB", "MB", "GB", "TB")
    amount = float(value)
    for unit in units:
        if abs(amount) < 1024 or unit == units[-1]:
            return f"{amount:.0f} {unit}" if unit == "B" else f"{amount:.1f} {unit}"
        amount /= 1024
    return f"{amount:.1f} TB"


def human_speed(value: float) -> str:
    return f"{human_bytes(value)}/s"


class TrafficMonitor(QObject):
    sample = Signal(object)
    link_changed = Signal(bool, str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._socket: TrafficSocket | None = None
        self._sample = TrafficSample()

    @property
    def latest(self) -> TrafficSample:
        return self._sample

    def start(self, port: int, secret: str) -> None:
        self.stop()
        self._socket = TrafficSocket(port, secret, parent=self)
        self._socket.traffic.connect(self._on_traffic)
        self._socket.connected.connect(lambda: self.link_changed.emit(True, ""))
        self._socket.disconnected.connect(self._on_disconnected)
        self._socket.start()

    def stop(self) -> None:
        if self._socket is not None:
            self._socket.stop_and_wait()
            self._socket.deleteLater()
            self._socket = None
        self._sample = TrafficSample()
        self.sample.emit(self._sample)

    def _on_traffic(self, payload: dict) -> None:
        try:
            self._sample = TrafficSample(
                up=int(payload.get("up", 0)),
                down=int(payload.get("down", 0)),
                up_total=int(payload.get("upTotal", 0)),
                down_total=int(payload.get("downTotal", 0)),
            )
        except (TypeError, ValueError):
            return
        self.sample.emit(self._sample)

    def _on_disconnected(self, reason: str) -> None:
        self.link_changed.emit(False, reason)
