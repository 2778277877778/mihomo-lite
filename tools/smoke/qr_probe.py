import sys
from pathlib import Path

import zxingcpp
from PIL import Image

bc = zxingcpp.create_barcode("https://example.test/sub?token=abc123", format=zxingcpp.barcode_format_from_str("QRCode"))
img = zxingcpp.write_barcode_to_image(bc, scale=6)
print("type:", type(img))
img.save("tools/smoke/qr_test.png")
print("saved:", Path("tools/smoke/qr_test.png").stat().st_size)

pil = Image.open("tools/smoke/qr_test.png")
result = zxingcpp.read_barcode(pil)
print("decoded:", result.text if result else None)
