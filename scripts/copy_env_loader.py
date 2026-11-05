"""テスト専用: コピー.env を明示的に読み込む。通常起動(.env)には影響しない。

必ず `backend.app.core.config` を import する前に load_copy_env() を呼ぶこと。
config.py の load_dotenv(.env) は override=False のため、ここで設定した値が優先される。
キーの値は一切出力しない。
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
COPY_ENV = ROOT / "コピー.env"
MANAGED = ("VERTEX_API_KEY", "GEMINI_MODEL", "GOOGLE_CLOUD_PROJECT", "GOOGLE_CLOUD_LOCATION")
LEGACY = ("GEMINI_API_KEY", "GOOGLE_API_KEY")


def load_copy_env(path: Path = COPY_ENV) -> list[str]:
    values = dotenv_values(path)
    if not values.get("VERTEX_API_KEY"):
        raise RuntimeError(f"{path.name} に VERTEX_API_KEY がありません。")
    for name in LEGACY:  # 旧キーとの混在防止
        os.environ.pop(name, None)
    loaded = []
    for name in MANAGED:
        value = values.get(name)
        if value:
            os.environ[name] = value
            loaded.append(name)
    return loaded
