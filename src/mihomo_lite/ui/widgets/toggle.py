"""A glossy pill switch that matches the liquid-glass surfaces."""

from __future__ import annotations

from PySide6.QtCore import Property, QEasingCurve, QPropertyAnimation, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import QAbstractButton


class ToggleSwitch(QAbstractButton):
    def __init__(self, parent=None, *, width: int = 60, height: int = 34) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._width = width
        self._height = height
        self.setFixedSize(width, height)
        self._offset = 0.0
        self._theme = "dark"
        self._anim = QPropertyAnimation(self, b"offset", self)
        self._anim.setDuration(160)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.toggled.connect(self._animate)

    def sizeHint(self) -> QSize:
        return QSize(self._width, self._height)

    def set_theme(self, theme: str) -> None:
        self._theme = theme
        self.update()

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
        track = QRectF(0.5, 0.5, self._width - 1, self._height - 1)

        if not self.isEnabled():
            track_fill = QColor(255, 255, 255, 26)
            knob = QColor(235, 240, 250, 90)
            border = QColor(255, 255, 255, 20)
        elif self.isChecked():
            gradient = QLinearGradient(track.topLeft(), track.bottomRight())
            gradient.setColorAt(0.0, QColor("#6f9bff"))
            gradient.setColorAt(1.0, QColor("#9377ff"))
            track_fill = gradient
            knob = QColor("#ffffff")
            border = QColor(255, 255, 255, 90)
        elif self._theme == "light":
            track_fill = QColor(16, 21, 33, 26)
            knob = QColor("#ffffff")
            border = QColor(16, 21, 33, 30)
        else:
            track_fill = QColor(255, 255, 255, 30)
            knob = QColor(247, 249, 255)
            border = QColor(255, 255, 255, 40)

        painter.setPen(QPen(border, 1.0))
        painter.setBrush(track_fill)
        painter.drawRoundedRect(track, radius, radius)

        margin = 3.5
        knob_size = self._height - margin * 2
        travel = self._width - knob_size - margin * 2
        x = margin + travel * self._offset
        knob_rect = QRectF(x, margin, knob_size, knob_size)

        if self.isChecked():
            glow = QRadialGradient(knob_rect.center(), knob_size)
            glow.setColorAt(0.0, QColor(255, 255, 255, 70))
            glow.setColorAt(1.0, QColor(255, 255, 255, 0))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(glow)
            painter.drawEllipse(knob_rect.adjusted(-3, -3, 3, 3))

        painter.setPen(QPen(QColor(255, 255, 255, 60), 0.8))
        painter.setBrush(knob)
        painter.drawEllipse(knob_rect)
