"""Decode QR code images into subscription URLs or raw YAML."""

from __future__ import annotations

from pathlib import Path

from mihomo_lite.utils.exceptions import MihomoLiteError


class QrError(MihomoLiteError):
    """The image does not contain a readable QR code."""


def decode_image(path: Path) -> str:
    """Return the text stored in the first QR code found in *path*."""
    try:
        import zxingcpp
        from PIL import Image
    except ImportError as exc:  # pragma: no cover - packaging regression
        raise QrError("QR support is not available in this build") from exc

    try:
        with Image.open(path) as image:
            image.load()
            result = zxingcpp.read_barcode(image)
    except QrError:
        raise
    except Exception as exc:  # noqa: BLE001 - pillow errors are varied
        raise QrError(f"cannot read the image: {exc}") from exc

    text = getattr(result, "text", "") if result is not None else ""
    text = (text or "").strip()
    if not text:
        raise QrError("no QR code found in the image")
    return text


def classify(text: str) -> tuple[str, str]:
    """Decide whether decoded text is a URL or an inline YAML profile."""
    if text.lower().startswith(("http://", "https://")):
        return "url", text
    lowered = text.lower()
    if "proxies:" in lowered or "proxy-groups:" in lowered or "proxy-providers:" in lowered:
        return "yaml", text
    raise QrError("the QR code is neither a subscription URL nor a YAML profile")
