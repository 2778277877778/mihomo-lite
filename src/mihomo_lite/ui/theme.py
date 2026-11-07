"""Loads QSS themes and exposes the colour tokens used by custom widgets."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QColor

from mihomo_lite.system.paths import resource_path

DARK = {
    "bg": "#14161a",
    "surface": "#1c1f26",
    "surface_alt": "#22262f",
    "border": "#2c313c",
    "text": "#e7e9ee",
    "text_dim": "#9aa3b2",
    "accent": "#4f8cff",
    "accent_soft": "#2b4a86",
    "ok": "#3ecf8e",
    "warn": "#f5a524",
    "error": "#f2585b",
}

LIGHT = {
    "bg": "#f5f6f8",
    "surface": "#ffffff",
    "surface_alt": "#eef0f4",
    "border": "#dde1e8",
    "text": "#1c1f26",
    "text_dim": "#6b7280",
    "accent": "#2563eb",
    "accent_soft": "#dbe6ff",
    "ok": "#0f9d63",
    "warn": "#b76e00",
    "error": "#d13438",
}


def palette(theme: str) -> dict[str, str]:
    return DARK if theme == "dark" else LIGHT


def qss_path(theme: str) -> Path:
    name = "dark.qss" if theme == "dark" else "light.qss"
    return resource_path("resources", "styles", name)


def load_stylesheet(theme: str) -> str:
    path = qss_path(theme)
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def color(theme: str, token: str) -> QColor:
    return QColor(palette(theme).get(token, "#ffffff"))
