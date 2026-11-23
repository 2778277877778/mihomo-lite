"""Status pill and metric tiles used by the dashboard."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from mihomo_lite.models.app_state import ConnectionState


class StatusPill(QLabel):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("StatusPill")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.set_state(ConnectionState.STOPPED)

    def set_state(self, state: ConnectionState) -> None:
        if self.property("state") == state.value:
            return
        self.setProperty("state", state.value)
        self.setText(state.label)
        self.style().unpolish(self)
        self.style().polish(self)


class MetricTile(QFrame):
    def __init__(self, title: str, value: str = "-", parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(2)

        self._label = QLabel(title.upper())
        self._label.setObjectName("MetricLabel")
        self._value = QLabel(value)
        self._value.setObjectName("Metric")
        self._value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self._label)
        layout.addWidget(self._value)

    def set_value(self, value: str) -> None:
        if self._value.text() != value:
            self._value.setText(value)


class KeyValueRow(QWidget):
    def __init__(self, key: str, value: str = "-", parent=None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(23)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 1, 0, 1)
        self._key = QLabel(key)
        self._key.setObjectName("Hint")
        self._value = QLabel(value)
        self._value.setObjectName("KeyValue")
        self._value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self._key)
        layout.addStretch(1)
        layout.addWidget(self._value)

    def set_value(self, value: str) -> None:
        if self._value.text() != value:
            self._value.setText(value)
