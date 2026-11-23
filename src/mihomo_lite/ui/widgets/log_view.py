"""Log viewer that follows the in-memory ring buffer by sequence number.

Polling keeps the logging module free of any Qt dependency. Sequence numbers
matter: once the ring buffer is full the oldest records are evicted, so a plain
length check would stop showing new lines entirely.
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
        self.setMaximumBlockCount(8000)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._last_seq = 0
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
        if not records:
            return

        first_seq = records[0][0]
        new_records = [record for record in records if record[0] > self._last_seq]
        if not new_records:
            return

        skipped = 0
        if self._last_seq and first_seq > self._last_seq + 1:
            skipped = first_seq - self._last_seq - 1

        bar = self.verticalScrollBar()
        at_bottom = bar.value() >= bar.maximum() - 4
        self.setUpdatesEnabled(False)
        try:
            if skipped:
                self.appendPlainText(f"[{skipped} earlier log lines were dropped]")
            for _seq, _level, _name, text in new_records:
                self.appendPlainText(text)
        finally:
            self.setUpdatesEnabled(True)
        self._last_seq = new_records[-1][0]
        if at_bottom:
            bar.setValue(bar.maximum())

    def clear_log(self) -> None:
        get_ring_buffer().clear()
        self.clear()
        self._last_seq = 0
