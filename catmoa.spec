# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 스펙 — macOS(.app) / Windows / Linux 공용 onedir 빌드."""
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

ROOT = Path(SPECPATH)
sys.path.insert(0, str(ROOT))
from src import __version__  # noqa: E402

datas = [(str(ROOT / "assets" / "icon.png"), "assets")]
datas += collect_data_files("googleapiclient", includes=["discovery_cache/documents/*.json"])
datas += collect_data_files("pdfminer")          # cmap 등
datas += collect_data_files("pypdfium2_raw")
datas += collect_data_files("pypdfium2")
binaries = collect_dynamic_libs("pypdfium2_raw") + collect_dynamic_libs("pypdfium2")

hiddenimports = (
    collect_submodules("keyring.backends")
    + ["googleapiclient.discovery_cache", "google.auth.transport.requests", "google_auth_oauthlib.flow",
       "PIL.ImageQt", "pypdfium2_raw"]
)

a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "numpy.testing", "pytest", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
              "PySide6.Qt3DCore", "PySide6.QtMultimedia", "PySide6.QtCharts", "PySide6.QtQuick", "PySide6.QtQml"],
    noarchive=False,
)
pyz = PYZ(a.pure)

icon = str(ROOT / "assets" / ("icon.ico" if sys.platform == "win32" else "icon.png"))

exe = EXE(
    pyz,
    a.scripts,
    exclude_binaries=True,
    name="catmoa",
    debug=False,
    strip=False,
    upx=False,
    console=False,
    icon=icon,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="catmoa")

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="catmoa.app",
        icon=icon,
        bundle_identifier="kr.catmoa.app",
        info_plist={
            "CFBundleName": "catmoa",
            "CFBundleDisplayName": "catmoa",
            "CFBundleShortVersionString": __version__,
            "CFBundleVersion": __version__,
            "LSUIElement": True,                 # Dock 아이콘 없이 떠 있는 위젯 앱
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "12.0",
        },
    )
