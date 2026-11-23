"""Animated wheel scrolling for Qt scroll areas.

Qt scrolls a fixed number of lines per wheel notch, which feels jumpy next to
the rest of the UI. This filter animates the scrollbar instead, and keeps
trackpad pixel deltas intact.
"""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QEvent, QObject, QPropertyAnimation, Qt
from PySide6.QtWidgets import QAbstractScrollArea, QScrollBar

_ANIMATION_MS = 180


class SmoothScroller(QObject):
    def __init__(
        self, area: QAbstractScrollArea, duration_ms: int = _ANIMATION_MS
    ) -> None:
        super().__init__(area)
        self._area = area
        self._vertical = QPropertyAnimation(area.verticalScrollBar(), b"value", self)
        self._horizontal = QPropertyAnimation(area.horizontalScrollBar(), b"value", self)
        for animation in (self._vertical, self._horizontal):
            animation.setEasingCurve(QEasingCurve.Type.OutCubic)
            animation.setDuration(duration_ms)
        area.viewport().installEventFilter(self)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # noqa: N802 - Qt naming
        if event.type() != QEvent.Type.Wheel or not self._area.isEnabled():
            return False
        modifiers = event.modifiers()
        if modifiers & Qt.KeyboardModifier.ControlModifier:
            return False

        vertical_bar = self._area.verticalScrollBar()
        horizontal_bar = self._area.horizontalScrollBar()
        pixel = event.pixelDelta()
        angle = event.angleDelta()

        step_v = self._wheel_step(pixel.y(), angle.y(), vertical_bar)
        step_h = self._wheel_step(pixel.x(), angle.x(), horizontal_bar)

        if modifiers & Qt.KeyboardModifier.ShiftModifier and not step_h:
            step_h, step_v = step_v, 0

        handled = False
        if step_v and self._scrollable(vertical_bar):
            self._animate(self._vertical, vertical_bar, vertical_bar.value() - step_v)
            handled = True
        if step_h and self._scrollable(horizontal_bar):
            self._animate(self._horizontal, horizontal_bar, horizontal_bar.value() - step_h)
            handled = True
        return handled

    @staticmethod
    def _scrollable(bar: QScrollBar) -> bool:
        return bar.maximum() > bar.minimum()

    @staticmethod
    def _wheel_step(pixels: int, angle: int, bar: QScrollBar) -> int:
        if pixels:
            return pixels
        if not angle:
            return 0
        return int(angle / 120 * max(bar.singleStep(), 16) * 3)

    @staticmethod
    def _animate(animation: QPropertyAnimation, bar: QScrollBar, target: int) -> None:
        target = max(bar.minimum(), min(bar.maximum(), int(target)))
        animation.stop()
        animation.setStartValue(bar.value())
        animation.setEndValue(target)
        animation.start()


def enable_smooth_scroll(area: QAbstractScrollArea) -> SmoothScroller:
    return SmoothScroller(area)
