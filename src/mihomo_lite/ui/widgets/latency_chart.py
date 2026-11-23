"""Latency fluctuation chart for the current node."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget


class LatencyChart(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._history: list[int] = []
        self._jitter = 0
        self.setMinimumHeight(124)

    def set_series(self, history: list[int], jitter: int = 0) -> None:
        self._history = [int(value) for value in history if value > 0][-60:]
        self._jitter = max(0, int(jitter))
        self.update()

    def clear(self) -> None:
        self._history = []
        self._jitter = 0
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt naming
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(12, 10, -12, -20)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(255, 255, 255, 6))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 14, 14)

        history = self._history
        if len(history) < 2:
            painter.setPen(QColor(160, 170, 190, 160))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Waiting for latency samples…")
            return

        peak = max(max(history), 1)
        low = min(history)
        span = max(peak - low, 10)
        top = low - span * 0.15
        bottom = peak + span * 0.15
        step = rect.width() / max(1, len(history) - 1)

        def y_for(value: float) -> float:
            ratio = (value - top) / (bottom - top)
            return rect.bottom() - ratio * rect.height()

        painter.setPen(QPen(QColor(255, 255, 255, 14), 1))
        for index in range(1, 4):
            y = rect.top() + rect.height() * index / 4
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))

        points = [
            QPointF(rect.left() + index * step, y_for(value))
            for index, value in enumerate(history)
        ]
        area = QPainterPath(QPointF(points[0].x(), rect.bottom()))
        for point in points:
            area.lineTo(point)
        area.lineTo(points[-1].x(), rect.bottom())
        area.closeSubpath()
        gradient = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        gradient.setColorAt(0.0, QColor(122, 162, 255, 120))
        gradient.setColorAt(1.0, QColor(122, 162, 255, 8))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(gradient)
        painter.drawPath(area)

        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(122, 162, 255), 2))
        for first, second in zip(points, points[1:], strict=False):
            painter.drawLine(first, second)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(122, 162, 255))
        painter.drawEllipse(points[-1], 3.2, 3.2)

        average = int(sum(history) / len(history))
        painter.setPen(QPen(QColor(255, 255, 255, 60), 1, Qt.PenStyle.DashLine))
        painter.drawLine(
            QPointF(rect.left(), y_for(average)), QPointF(rect.right(), y_for(average))
        )

        painter.setPen(QColor(190, 200, 218, 220))
        font = QFont(self.font())
        font.setPointSizeF(max(7.5, font.pointSizeF() - 2))
        painter.setFont(font)
        painter.drawText(
            QRectF(rect.left(), rect.bottom() + 4, rect.width(), 16),
            Qt.AlignmentFlag.AlignLeft,
            f"last {history[-1]} ms   avg {average} ms   jitter ±{self._jitter} ms",
        )
