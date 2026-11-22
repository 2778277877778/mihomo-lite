"""Single-instance guard.

Two instances would fight over the same ports and the same system proxy, so the
second instance hands over to the first one and exits. A quit message lets the
uninstaller ask the running copy to restore the proxy before it is removed.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

log = logging.getLogger(__name__)

_SERVER_NAME = "MihomoLite.SingleInstance"
_ACTIVATE = b"activate\n"
_QUIT = b"quit\n"


class SingleInstance(QObject):
    """Acquire a lock; emit activated() when another launch asks for the window."""

    activated = Signal()
    quit_requested = Signal()

    def __init__(self, lock_path: Path, parent: QObject | None = None) -> None:
        super().__init__(parent)
        from PySide6.QtCore import QLockFile

        self._lock = QLockFile(str(lock_path))
        self._lock.setStaleLockTime(0)
        self._is_primary = self._lock.tryLock(300)
        self._server: QLocalServer | None = None

    @property
    def is_primary(self) -> bool:
        return self._is_primary

    def wait_for_primary(self, timeout_ms: int = 2500, interval_ms: int = 120) -> bool:
        """Retry the lock briefly.

        An elevated relaunch can start before the previous process has finished
        shutting down; without this window the new process would see the lock as
        taken and exit silently.
        """
        deadline = time.monotonic() + max(0, timeout_ms) / 1000
        while not self._is_primary and time.monotonic() < deadline:
            if self._lock.tryLock(interval_ms):
                self._is_primary = True
                break
            time.sleep(interval_ms / 1000)
        return self._is_primary

    def start_server(self) -> None:
        if not self._is_primary:
            return
        QLocalServer.removeServer(_SERVER_NAME)
        self._server = QLocalServer(self)
        if not self._server.listen(_SERVER_NAME):
            log.warning("could not start the single-instance server: %s", self._server.errorString())
            return
        self._server.newConnection.connect(self._on_new_connection)

    def _on_new_connection(self) -> None:
        if self._server is None:
            return
        while self._server.hasPendingConnections():
            socket = self._server.nextPendingConnection()
            if socket is None:
                continue
            socket.readyRead.connect(lambda s=socket: self._read(s))
            socket.disconnected.connect(socket.deleteLater)

    def _read(self, socket: QLocalSocket) -> None:
        data = bytes(socket.readAll()).strip()
        if data == _QUIT.strip():
            log.info("another process asked this instance to quit")
            self.quit_requested.emit()
        elif data == _ACTIVATE.strip():
            log.info("another instance asked for the window")
            self.activated.emit()

    @staticmethod
    def notify_existing(message: str = "activate") -> bool:
        """Ask the running instance to show itself or quit. True on success."""
        payload = _QUIT if message == "quit" else _ACTIVATE
        socket = QLocalSocket()
        socket.connectToServer(_SERVER_NAME)
        if not socket.waitForConnected(500):
            return False
        socket.write(payload)
        socket.flush()
        socket.waitForBytesWritten(500)
        socket.disconnectFromServer()
        return True

    def release(self) -> None:
        if self._server is not None:
            self._server.close()
            self._server = None
        if self._is_primary:
            self._lock.unlock()
            self._is_primary = False
