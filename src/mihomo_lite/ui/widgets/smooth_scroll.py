"""Momentum ("inertial") wheel scrolling for Qt scroll areas.

Wheel notches feed a velocity instead of a fixed jump; a 60 fps timer integrates
the velocity with exponential friction, so the content keeps gliding and eases
out the way macOS does. Precise (trackpad) deltas are applied immediately and
only contribute a small flick, which keeps the 1:1 feel of a touchpad.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtWidgets import QAbstractScrollArea, QScrollBar

_FRAME_MS = 16
_FRICTION = 0.92
_MIN_SPEED = 0.35
_WHEEL_VELOCITY = 5.0  # px per frame for one classic 120-unit notch
_TRACKPAD_GAIN = 0.08
_inverted = False


def set_scroll_inverted(value: bool) -> None:
    """Flip the wheel/touchpad direction without touching the rest of the app."""
    global _inverted
    _inverted = bool(value)


class SmoothScroller(QObject):
    def __init__(self, area: QAbstractScrollArea) -> None:
        super().__init__(area)
        self._area = area
        self._timer = QTimer(self)
        self._timer.setInterval(_FRAME_MS)
        self._timer.timeout.connect(self._step)
        self._velocity_v = 0.0
        self._velocity_h = 0.0
        self._position_v = 0.0
        self._position_h = 0.0
        self._synced = False
        area.viewport().installEventFilter(self)

    # -- input -------------------------------------------------------------
    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # noqa: N802 - Qt naming
        if event.type() != QEvent.Type.Wheel or not self._area.isEnabled():
            return False
        modifiers = event.modifiers()
        if modifiers & Qt.KeyboardModifier.ControlModifier:
            return False

        vertical_bar = self._area.verticalScrollBar()
        horizontal_bar = self._area.horizontalScrollBar()
        pixels = event.pixelDelta()
        angle = event.angleDelta()

        velocity_v = self._velocity_from(angle.y(), pixels.y())
        velocity_h = self._velocity_from(angle.x(), pixels.x())
        if modifiers & Qt.KeyboardModifier.ShiftModifier and not velocity_h:
            velocity_h, velocity_v = velocity_v, 0.0

        handled = False
        if velocity_v and self._scrollable(vertical_bar):
            self._sync_positions()
            self._velocity_v += velocity_v
            handled = True
        if velocity_h and self._scrollable(horizontal_bar):
            self._sync_positions()
            self._velocity_h += velocity_h
            handled = True

        if handled:
            self._clamp_velocity()
            if not self._timer.isActive():
                self._timer.start()
        return handled

    @staticmethod
    def _velocity_from(angle: int, pixels: int) -> float:
        if pixels:
            return pixels * _TRACKPAD_GAIN
        if not angle:
            return 0.0
        return angle / 120 * _WHEEL_VELOCITY

    def _sync_positions(self) -> None:
        if self._timer.isActive():
            return
        self._position_v = float(self._area.verticalScrollBar().value())
        self._position_h = float(self._area.horizontalScrollBar().value())

    def _clamp_velocity(self) -> None:
        limit = 90.0
        self._velocity_v = max(-limit, min(limit, self._velocity_v))
        self._velocity_h = max(-limit, min(limit, self._velocity_h))

    # -- animation ---------------------------------------------------------
    def _step(self) -> None:
        self._velocity_v *= _FRICTION
        self._velocity_h *= _FRICTION

        moving = False
        moving |= self._advance(
            self._area.verticalScrollBar(), "_position_v", "_velocity_v", horizontal=False
        )
        moving |= self._advance(
            self._area.horizontalScrollBar(), "_position_h", "_velocity_h", horizontal=True
        )
        if not moving:
            self._timer.stop()

    @staticmethod
    def _axis_delta(velocity: float, *, horizontal: bool) -> float:
        """Qt wheel deltas: forward (positive) means scroll up / to the right.

        Scrollbar values grow downwards, so vertical motion is inverted while
        horizontal motion keeps its sign.
        """
        delta = velocity if horizontal else -velocity
        return -delta if _inverted else delta

    def _advance(
        self,
        bar: QScrollBar,
        position_name: str,
        velocity_name: str,
        *,
        horizontal: bool,
    ) -> bool:
        velocity = getattr(self, velocity_name)
        if abs(velocity) < _MIN_SPEED:
            setattr(self, velocity_name, 0.0)
            return False

        position = getattr(self, position_name) + self._axis_delta(
            velocity, horizontal=horizontal
        )
        minimum, maximum = bar.minimum(), bar.maximum()
        if position <= minimum or position >= maximum:
            position = float(max(minimum, min(maximum, position)))
            bar.setValue(int(round(position)))
            setattr(self, position_name, position)
            setattr(self, velocity_name, 0.0)
            return False

        bar.setValue(int(round(position)))
        setattr(self, position_name, position)
        return True

    @staticmethod
    def _scrollable(bar: QScrollBar) -> bool:
        return bar.maximum() > bar.minimum()


def enable_smooth_scroll(area: QAbstractScrollArea) -> SmoothScroller:
    return SmoothScroller(area)
