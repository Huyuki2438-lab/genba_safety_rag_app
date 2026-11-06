"""テスト専用: コピー.env を明示的に読み込む。通常起動(.env)には影響しない。

config.json がある環境では config.py が secrets.env を override=True で読むため、
config の import 後に apply_copy_env_to_config() でコピー.envを再適用する。
キーの値は一切出力しない。
"""
from __future__ import annotations

import os
from pathlib import Path
from types import ModuleType
from typing import Any

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


def apply_copy_env_to_config(config_module: ModuleType, path: Path = COPY_ENV) -> tuple[list[str], Any]:
    """コピー.envを再適用し、configモジュールのSettingsを作り直す。"""
    loaded = load_copy_env(path)
    refreshed_settings = config_module.Settings()
    config_module.settings = refreshed_settings
    return loaded, refreshed_settings
