"""Small control refinements shared by the pages."""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QComboBox


class Combo(QComboBox):
    """A combo box that keeps a visible chevron under the custom stylesheet."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(32)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt naming
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = self.palette().color(self.foregroundRole())
        color.setAlpha(170)
        painter.setPen(color)
        painter.drawText(
            QRectF(self.width() - 28, 0, 22, self.height()),
            Qt.AlignmentFlag.AlignCenter,
            "▾",
        )
