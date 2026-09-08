# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
root = Path(SPECPATH)
a = Analysis([str(root / "desktop_app.py")], pathex=[str(root)],
    datas=[(str(root / "frontend_build"), "frontend_build"),
           (str(root / "templates" / "report.html"), "templates"),
           (str(root / "static" / "pdf.css"), "static"),
           (str(root / "static" / "icons" / "app_icon.ico"), "static/icons"),
           (str(root / "backend/app/core/prompts/templates"), "backend/app/core/prompts/templates")],
    hiddenimports=["uvicorn.loops.asyncio", "uvicorn.protocols.http.h11_impl", "uvicorn.lifespan.on"],
    excludes=["webview", "pythonnet", "clr", "sqlalchemy", "psycopg", "tkinter", "numpy", "PIL", "pytest"],
    noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name="KY安全管理", console=False,
          debug=False, strip=False, upx=False, disable_windowed_traceback=True,
          icon=str(root / "static/icons/app_icon.ico"))
