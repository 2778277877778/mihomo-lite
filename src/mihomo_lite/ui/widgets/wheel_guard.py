"""Stop scroll wheels from changing inputs the user did not focus.

By default QComboBox and QSpinBox change their value on every wheel notch, even
when they are not focused. Scrolling the settings page therefore silently edits
ports, stack, language and interval. This application-level filter consumes the
wheel over such controls unless they have focus and forwards the scroll to the
surrounding page instead.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject
from PySide6.QtWidgets import (
    QAbstractScrollArea,
    QAbstractSpinBox,
    QApplication,
    QComboBox,
)

_SENSITIVE = (QComboBox, QAbstractSpinBox)


class WheelGuard(QObject):
    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # noqa: N802 - Qt naming
        if event.type() != QEvent.Type.Wheel:
            return False
        if not isinstance(obj, _SENSITIVE):
            return False
        widget = obj
        if widget.hasFocus():
            return False
        self._forward_scroll(widget, event)
        return True

    @staticmethod
    def _scroll_area_for(widget) -> QAbstractScrollArea | None:
        parent = widget.parent()
        while parent is not None:
            if isinstance(parent, QAbstractScrollArea):
                return parent
            parent = parent.parent()
        return None

    def _forward_scroll(self, widget, event) -> None:
        area = self._scroll_area_for(widget)
        if area is None:
            return
        bar = area.verticalScrollBar()
        delta = self._scroll_delta(event.angleDelta().y(), bar.singleStep())
        if delta:
            bar.setValue(bar.value() - delta)

    @staticmethod
    def _scroll_delta(angle: int, step: int) -> int:
        if not angle:
            return 0
        return int(angle / 120 * max(step, 16) * 3)


def install_wheel_guard(app: QApplication) -> WheelGuard:
    guard = WheelGuard(app)
    app.installEventFilter(guard)
    app._wheel_guard = guard  # keep a strong reference
    return guard
