import pytest
import qrcode
from PIL import Image

from mihomo_lite.core import qr


def make_qr(path, text):
    qrcode.make(text).save(path)


def test_decode_url(tmp_path):
    path = tmp_path / "sub.png"
    make_qr(path, "https://example.test/sub?token=abc")
    text = qr.decode_image(path)
    assert text.startswith("https://")
    assert qr.classify(text)[0] == "url"


def test_decode_inline_yaml(tmp_path):
    path = tmp_path / "inline.png"
    make_qr(path, "proxies:\n  - {name: a, type: socks5, server: 127.0.0.1, port: 1}\n")
    text = qr.decode_image(path)
    assert qr.classify(text)[0] == "yaml"


def test_blank_image_has_no_qr(tmp_path):
    path = tmp_path / "blank.png"
    Image.new("RGB", (120, 120), "white").save(path)
    with pytest.raises(qr.QrError):
        qr.decode_image(path)


def test_classify_rejects_other_text():
    with pytest.raises(qr.QrError):
        qr.classify("hello world")
