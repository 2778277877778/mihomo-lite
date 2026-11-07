"""Generate the application icon (PNG + ICO) with Pillow.

Run from the repository root:  python scripts/make_icons.py
The output is committed so builds do not depend on Pillow.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
ICON_DIR = ROOT / "src" / "mihomo_lite" / "resources" / "icons"
SIZE = 512
COLOR = (79, 140, 255, 255)
WHITE = (255, 255, 255, 255)


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for name in ("seguisb.ttf", "segoeuib.ttf", "arialbd.ttf"):
        path = Path("C:/Windows/Fonts") / name
        if path.exists():
            try:
                return ImageFont.truetype(str(path), size)
            except OSError:
                continue
    return ImageFont.load_default()


def build() -> Image.Image:
    image = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    radius = int(SIZE * 0.26)
    draw.rounded_rectangle((0, 0, SIZE - 1, SIZE - 1), radius=radius, fill=COLOR)

    font = _font(int(SIZE * 0.5))
    text = "M"
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    draw.text(
        ((SIZE - (right - left)) / 2 - left, (SIZE - (bottom - top)) / 2 - top - SIZE * 0.02),
        text,
        font=font,
        fill=WHITE,
    )
    return image


def main() -> None:
    ICON_DIR.mkdir(parents=True, exist_ok=True)
    image = build()
    png = ICON_DIR / "app.png"
    image.save(png, "PNG")
    image.save(
        ICON_DIR / "app.ico",
        format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    print(f"wrote {png} and {ICON_DIR / 'app.ico'}")


if __name__ == "__main__":
    main()
