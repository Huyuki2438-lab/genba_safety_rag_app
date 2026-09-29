"""PC-local paths shared by desktop_app.py and the FastAPI app.

Kept dependency-free (no config.py import) so it can be used before/without
loading project configuration, e.g. by desktop_app.py at very early startup.
"""
from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "KY安全管理"


def local_data_root() -> Path:
    """PC毎に固定される書き込み用ローカルディレクトリ (ログ・再起動フラグ等)。"""
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        return Path(local_appdata) / APP_NAME
    return Path.home() / f".{APP_NAME.lower()}"


def restart_flag_path() -> Path:
    """初期設定完了後の再起動を desktop_app.py へ伝えるためのマーカーファイル。"""
    return local_data_root() / "restart.flag"
