"""Log viewer that polls the in-memory ring buffer.

Polling keeps the logging module free of any Qt dependency.
"""

from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QPlainTextEdit

from mihomo_lite.utils.logger import get_ring_buffer


class LogView(QPlainTextEdit):
    def __init__(self, parent=None, *, poll_ms: int = 300) -> None:
        super().__init__(parent)
        self.setObjectName("LogView")
        self.setReadOnly(True)
        self.setMaximumBlockCount(5000)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._seen = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)
        self._timer.start(poll_ms)
        self._poll()

    def _poll(self) -> None:
        records = get_ring_buffer().snapshot()
        if len(records) < self._seen:
            self.clear()
            self._seen = 0
        if len(records) == self._seen:
            return
        for _level, _name, text in records[self._seen :]:
            self.appendPlainText(text)
        self._seen = len(records)
        bar = self.verticalScrollBar()
        bar.setValue(bar.maximum())

    def clear_log(self) -> None:
        get_ring_buffer().clear()
        self.clear()
        self._seen = 0
