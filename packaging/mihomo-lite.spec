# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec: onedir build with the QSS resources and the app icon."""

from pathlib import Path

ROOT = Path(SPECPATH).parent
SRC = ROOT / "src"

block_cipher = None

datas = [
    (str(SRC / "mihomo_lite" / "resources" / "styles"), "mihomo_lite/resources/styles"),
    (str(SRC / "mihomo_lite" / "resources" / "icons"), "mihomo_lite/resources/icons"),
]

a = Analysis(
    [str(SRC / "mihomo_lite" / "main.py")],
    pathex=[str(SRC)],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtQml",
        "PySide6.QtQuick",
        "PySide6.Qt3DCore",
        "PySide6.QtMultimedia",
        "PySide6.QtPdf",
        "PySide6.QtCharts",
        "PySide6.QtBluetooth",
        "PySide6.QtSql",
        "PySide6.QtTest",
    ],
    cipher=block_cipher,
    noarchive=False,
)

# Qt ships ~7 MB of translations we never use (all UI strings are ours), and the
# unused QML/3D plugins were already excluded above.
a.datas = [
    entry
    for entry in a.datas
    if "translations" not in entry[0].replace("\\", "/").lower()
]

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MihomoLite",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(SRC / "mihomo_lite" / "resources" / "icons" / "app.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="MihomoLite",
)
