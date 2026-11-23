"""Log viewer that polls the in-memory ring buffer.

Polling keeps the logging module free of any Qt dependency.
"""

from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QPlainTextEdit

from mihomo_lite.utils.logger import get_ring_buffer


class LogView(QPlainTextEdit):
    def __init__(self, parent=None, *, poll_ms: int = 400) -> None:
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

    def showEvent(self, event) -> None:  # noqa: N802 - Qt naming
        super().showEvent(event)
        self._poll()

    def _poll(self) -> None:
        # Hidden pages should not spend time laying out text they never show.
        if not self.isVisible():
            return
        records = get_ring_buffer().snapshot()
        if len(records) < self._seen:
            self.clear()
            self._seen = 0
        if len(records) == self._seen:
            return
        bar = self.verticalScrollBar()
        at_bottom = bar.value() >= bar.maximum() - 4
        self.setUpdatesEnabled(False)
        try:
            for _level, _name, text in records[self._seen :]:
                self.appendPlainText(text)
        finally:
            self.setUpdatesEnabled(True)
        self._seen = len(records)
        if at_bottom:
            bar.setValue(bar.maximum())

    def clear_log(self) -> None:
        get_ring_buffer().clear()
        self.clear()
        self._seen = 0
