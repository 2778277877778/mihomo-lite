import zxingcpp
bc = zxingcpp.create_barcode("hello", format=zxingcpp.barcode_format_from_str("QRCode"))
img = zxingcpp.write_barcode_to_image(bc, scale=4)
print([a for a in dir(img) if not a.startswith("_")])
print("shape:", getattr(img, "shape", None))
print("dtype:", getattr(img, "dtype", None))
