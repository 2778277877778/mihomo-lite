"""An iOS-style switch used for the main connect button and settings toggles."""

from __future__ import annotations

from PySide6.QtCore import Property, QEasingCurve, QPropertyAnimation, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QAbstractButton


class ToggleSwitch(QAbstractButton):
    def __init__(self, parent=None, *, width: int = 56, height: int = 30) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._width = width
        self._height = height
        self.setFixedSize(width, height)
        self._offset = 0.0
        self._anim = QPropertyAnimation(self, b"offset", self)
        self._anim.setDuration(140)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self.toggled.connect(self._animate)

    def sizeHint(self) -> QSize:
        return QSize(self._width, self._height)

    def _animate(self, checked: bool) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._offset)
        self._anim.setEndValue(1.0 if checked else 0.0)
        self._anim.start()

    def get_offset(self) -> float:
        return self._offset

    def set_offset(self, value: float) -> None:
        self._offset = float(value)
        self.update()

    offset = Property(float, get_offset, set_offset)

    def setChecked(self, checked: bool) -> None:  # noqa: N802 - Qt naming
        super().setChecked(checked)
        self._offset = 1.0 if checked else 0.0
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt naming
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        radius = self._height / 2
        track = QRectF(0, 0, self._width, self._height)

        if not self.isEnabled():
            track_color = QColor("#2c313c")
            knob_color = QColor("#5b6270")
        elif self.isChecked():
            track_color = QColor("#4f8cff")
            knob_color = QColor("#ffffff")
        else:
            track_color = QColor("#3a4150")
            knob_color = QColor("#dfe3ea")

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(track_color)
        painter.drawRoundedRect(track, radius, radius)

        margin = 3.0
        knob_size = self._height - margin * 2
        travel = self._width - knob_size - margin * 2
        x = margin + travel * self._offset
        painter.setBrush(knob_color)
        painter.drawEllipse(QRectF(x, margin, knob_size, knob_size))
