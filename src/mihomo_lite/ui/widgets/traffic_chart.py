"""A dependency-free two-series traffic chart (download area + upload line)."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from mihomo_lite.core.traffic_monitor import human_speed


class TrafficChart(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._samples: tuple[tuple[int, int], ...] = ()
        self.setMinimumHeight(160)

    def set_samples(self, samples: tuple[tuple[int, int], ...]) -> None:
        self._samples = samples
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt naming
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(10, 10, -10, -24)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(255, 255, 255, 8))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 18, 18)

        samples = self._samples[-120:]
        if len(samples) < 2:
            painter.setPen(QColor(160, 170, 190, 160))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Waiting for traffic…")
            return

        peak = max(max(down for down, _ in samples), max(up for _, up in samples), 1)
        step = rect.width() / max(1, len(samples) - 1)

        def points(series: int) -> list[QPointF]:
            result = []
            for index, sample in enumerate(samples):
                value = sample[series] / peak
                result.append(
                    QPointF(rect.left() + index * step, rect.bottom() - value * rect.height())
                )
            return result

        down_points = points(0)
        up_points = points(1)

        area = QPainterPath(QPointF(down_points[0].x(), rect.bottom()))
        for point in down_points:
            area.lineTo(point)
        area.lineTo(down_points[-1].x(), rect.bottom())
        area.closeSubpath()
        gradient = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        gradient.setColorAt(0.0, QColor(122, 162, 255, 150))
        gradient.setColorAt(1.0, QColor(122, 162, 255, 10))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(gradient)
        painter.drawPath(area)

        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(122, 162, 255), 2))
        for first, second in zip(down_points, down_points[1:]):
            painter.drawLine(first, second)
        painter.setPen(QPen(QColor(70, 224, 160), 1.5))
        for first, second in zip(up_points, up_points[1:]):
            painter.drawLine(first, second)

        painter.setPen(QColor(170, 180, 200, 200))
        font = QFont(self.font())
        font.setPointSizeF(max(7.5, font.pointSizeF() - 2))
        painter.setFont(font)
        painter.drawText(
            QRectF(rect.left(), rect.bottom() + 4, rect.width(), 18),
            Qt.AlignmentFlag.AlignLeft,
            f"peak {human_speed(peak)}",
        )
