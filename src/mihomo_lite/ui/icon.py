"""Programmatically drawn icons - no binary assets, deterministic output."""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap

from mihomo_lite.models.app_state import ConnectionState

_STATE_COLORS = {
    ConnectionState.STOPPED: "#6b7280",
    ConnectionState.STARTING: "#f5a524",
    ConnectionState.CONNECTED: "#3ecf8e",
    ConnectionState.STOPPING: "#f5a524",
    ConnectionState.ERROR: "#f2585b",
}


def _pixmap(size: int, state: ConnectionState, *, badge: bool) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    body = QColor("#4f8cff")
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(body)
    painter.drawRoundedRect(QRectF(0, 0, size, size), size * 0.26, size * 0.26)

    painter.setPen(QColor("#ffffff"))
    font = QFont("Segoe UI", int(size * 0.44))
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(
        QRectF(0, -size * 0.03, size, size),
        Qt.AlignmentFlag.AlignCenter,
        "M",
    )

    if badge:
        dot = size * 0.34
        painter.setBrush(QColor(_STATE_COLORS.get(state, "#6b7280")))
        painter.setPen(QColor("#14161a"))
        painter.drawEllipse(QRectF(size - dot - 1, size - dot - 1, dot, dot))

    painter.end()
    return pixmap


def app_icon() -> QIcon:
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(_pixmap(size, ConnectionState.STOPPED, badge=False))
    return icon


def tray_icon(state: ConnectionState) -> QIcon:
    icon = QIcon()
    for size in (16, 24, 32, 48, 64):
        icon.addPixmap(_pixmap(size, state, badge=True))
    return icon


def save_app_icon_png(path: str) -> None:
    _pixmap(256, ConnectionState.STOPPED, badge=False).save(path, "PNG")
