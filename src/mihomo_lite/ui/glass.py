"""Liquid-glass helpers: window acrylic, rounded/clipped shell, aurora backdrop.

Qt cannot blur "what is behind" a widget, so the frosted look comes from two
layers that work together:

* the top-level window asks Windows for an acrylic backdrop, which really does
  blur the desktop behind the app;
* the shell paints soft colour fields with low alpha and clips to a large
  rounded rectangle, so every translucent surface above it reads as glass.
"""

from __future__ import annotations

import ctypes
import logging
import sys
from ctypes import wintypes

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QLinearGradient,
    QPainter,
    QPixmap,
    QRadialGradient,
)
from PySide6.QtWidgets import QWidget

log = logging.getLogger(__name__)

ACCENT_ENABLE_ACRYLICBLURBEHIND = 4
WCA_ACCENT_POLICY = 19
DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWCP_ROUND = 2


class _AccentPolicy(ctypes.Structure):
    _fields_ = [
        ("AccentState", ctypes.c_int),
        ("AccentFlags", ctypes.c_int),
        ("GradientColor", ctypes.c_uint),
        ("AnimationId", ctypes.c_int),
    ]


class _WindowCompositionAttributeData(ctypes.Structure):
    _fields_ = [
        ("Attribute", ctypes.c_int),
        ("Data", ctypes.c_void_p),
        ("SizeOfData", ctypes.c_size_t),
    ]


def _hwnd(widget: QWidget) -> int:
    try:
        return int(widget.winId())
    except Exception:  # noqa: BLE001 - window may not exist yet
        return 0


def enable_acrylic(widget: QWidget, *, tint: int = 0x99160E0A) -> bool:
    """Ask Windows for an acrylic backdrop behind *widget* (AABBGGRR tint)."""
    if sys.platform != "win32":
        return False
    hwnd = _hwnd(widget)
    if not hwnd:
        return False
    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        policy = _AccentPolicy(ACCENT_ENABLE_ACRYLICBLURBEHIND, 2, tint, 0)
        data = _WindowCompositionAttributeData(
            WCA_ACCENT_POLICY,
            ctypes.cast(ctypes.pointer(policy), ctypes.c_void_p),
            ctypes.sizeof(policy),
        )
        result = user32.SetWindowCompositionAttribute(hwnd, ctypes.byref(data))
        return bool(result)
    except Exception as exc:  # noqa: BLE001 - cosmetic only
        log.debug("acrylic backdrop unavailable: %s", exc)
        return False


def set_window_attributes(widget: QWidget, *, dark: bool = True) -> None:
    """Rounded corners on Windows 11 plus a matching title-less frame."""
    if sys.platform != "win32":
        return
    hwnd = _hwnd(widget)
    if not hwnd:
        return
    try:
        dwm = ctypes.WinDLL("dwmapi", use_last_error=True)
        corner = ctypes.c_int(DWMWCP_ROUND)
        dwm.DwmSetWindowAttribute(
            wintypes.HWND(hwnd),
            DWMWA_WINDOW_CORNER_PREFERENCE,
            ctypes.byref(corner),
            ctypes.sizeof(corner),
        )
        immersive = ctypes.c_int(1 if dark else 0)
        dwm.DwmSetWindowAttribute(
            wintypes.HWND(hwnd),
            DWMWA_USE_IMMERSIVE_DARK_MODE,
            ctypes.byref(immersive),
            ctypes.sizeof(immersive),
        )
    except Exception as exc:  # noqa: BLE001 - cosmetic only
        log.debug("window corner preference unavailable: %s", exc)


class AuroraBackdrop:
    """Soft colour fields painted under the glass surfaces."""

    def __init__(self, theme: str = "dark", radius: float = 20.0) -> None:
        self.theme = theme
        self.radius = radius
        #: When the OS refuses to blur the backdrop we paint an almost opaque
        #: base instead, otherwise the desktop would show through unblurred.
        self.flat = False
        # Gradients are expensive: render them once per size/theme and blit.
        self._cache = None
        self._cache_key = None

    def invalidate(self) -> None:
        self._cache = None
        self._cache_key = None

    def set_theme(self, theme: str) -> None:
        if theme != self.theme:
            self.theme = theme
            self.invalidate()

    def _blobs(self) -> list[tuple[float, float, float, QColor]]:
        if self.theme == "dark":
            return [
                (0.16, 0.02, 0.62, QColor(109, 93, 252, 52)),
                (0.90, 0.16, 0.54, QColor(53, 208, 255, 34)),
                (0.74, 0.95, 0.66, QColor(255, 95, 162, 26)),
                (0.06, 0.90, 0.48, QColor(70, 224, 160, 20)),
            ]
        return [
            (0.14, 0.00, 0.66, QColor(120, 152, 255, 78)),
            (0.94, 0.18, 0.56, QColor(120, 220, 255, 58)),
            (0.76, 0.98, 0.66, QColor(255, 158, 206, 50)),
            (0.06, 0.88, 0.50, QColor(126, 238, 198, 42)),
        ]

    def paint(self, painter: QPainter, rect: QRectF) -> None:
        size = rect.size().toSize()
        key = (size.width(), size.height(), self.theme, self.flat, round(self.radius, 1))
        if self._cache is None or self._cache_key != key:
            pixmap = QPixmap(size)
            pixmap.fill(Qt.GlobalColor.transparent)
            inner = QPainter(pixmap)
            inner.setRenderHint(QPainter.RenderHint.Antialiasing)
            self._paint_fields(inner, QRectF(0, 0, size.width(), size.height()))
            inner.end()
            self._cache = pixmap
            self._cache_key = key
        painter.drawPixmap(rect.topLeft(), self._cache)

    def _paint_fields(self, painter: QPainter, rect: QRectF) -> None:
        if self.theme == "dark":
            base = QLinearGradient(rect.topLeft(), rect.bottomRight())
            base.setColorAt(0.0, QColor(14, 18, 30, 250 if self.flat else 168))
            base.setColorAt(0.55, QColor(10, 13, 22, 252 if self.flat else 190))
            base.setColorAt(1.0, QColor(9, 11, 19, 253 if self.flat else 205))
        else:
            base = QLinearGradient(rect.topLeft(), rect.bottomRight())
            base.setColorAt(0.0, QColor(248, 250, 255, 252 if self.flat else 185))
            base.setColorAt(1.0, QColor(233, 238, 249, 254 if self.flat else 215))
        painter.fillRect(rect, base)

        for cx, cy, spread, color in self._blobs():
            center = QPointF(rect.left() + rect.width() * cx, rect.top() + rect.height() * cy)
            radius = max(rect.width(), rect.height()) * spread
            gradient = QRadialGradient(center, radius)
            gradient.setColorAt(0.0, color)
            fade = QColor(color)
            fade.setAlpha(0)
            gradient.setColorAt(1.0, fade)
            painter.fillRect(rect, gradient)
