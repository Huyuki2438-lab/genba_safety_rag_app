# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller ビルド定義 (onedir / windowed)。

`build_exe.ps1` から `pyinstaller desktop_app.spec` として呼び出す想定。
onedir 方式を採用する理由は BUILD_NOTES.md を参照。
"""

import sys
from pathlib import Path

block_cipher = None

PROJECT_ROOT = Path(SPECPATH)

# backend.app.core.prompts.manager が実行時に Path(__file__).parent 相対で
# 参照する jinja2 テンプレート。モジュールのパッケージ構造の中に配置する。
datas = [
    (
        str(PROJECT_ROOT / "backend" / "app" / "core" / "prompts" / "templates"),
        "backend/app/core/prompts/templates",
    ),
]

hiddenimports = [
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "webview.platforms.edgechromium",
]

a = Analysis(
    ["desktop_app.py"],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="GenbaSafetyRAGApp",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # 黒いコンソール画面を出さない
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(PROJECT_ROOT / "static" / "icons" / "app_icon.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="GenbaSafetyRAGApp",
)
