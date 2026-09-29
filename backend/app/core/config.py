from __future__ import annotations

import os
import json
import sys
from pathlib import Path
from dotenv import load_dotenv

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _compute_base_dir() -> Path:
    """アプリの基準ディレクトリを求める。

    PyInstaller (onedir) でexe化した場合、__file__ はビルド内部の展開先を
    指してしまうため、実際にexeが置かれているフォルダ(ネットワーク共有上の
    UNCパス等も含む)を基準にする必要がある。
    """
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent.parent.parent


BASE_DIR = _compute_base_dir()
APP_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else BASE_DIR
CONFIG_FILE = Path(os.environ.get("KY_CONFIG_FILE", str(APP_DIR / "config.json")))
PROJECT = {}


def _load_project_config(path: Path) -> dict:
    """config.jsonを読み込み、具体的な理由が分かる日本語メッセージで検証する。

    data_root はNAS(UNCパス)・ローカルフォルダのどちらも許容する。
    任意で storage_type ("local" | "network") を書けるが、
    保存先の種類はdata_rootの形から自動判定するため未指定でもよい
    (既存のconfig.jsonとの後方互換のため)。
    """
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise RuntimeError(f"config.jsonを読み込めません（{path}）。ファイルの存在とアクセス権限を確認してください。詳細: {exc}") from None
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "config.jsonの形式が正しくありません（JSON構文エラー）。"
            f"{exc.lineno}行目付近を確認してください。"
            "パス中のバックスラッシュは2個ずつ記載してください"
            "（例: ローカル\"C:\\\\KYデータ\"、NAS\"\\\\\\\\サーバー名\\\\共有名\\\\フォルダ\"）。"
            f" 詳細: {exc.msg}"
        ) from None
    if not isinstance(data, dict):
        raise RuntimeError("config.jsonの内容が正しくありません。project_id・project_name・data_rootを持つオブジェクト形式にしてください。") from None
    allowed_keys = {"project_id", "project_name", "data_root", "storage_type"}
    unknown = set(data) - allowed_keys
    if unknown:
        raise RuntimeError(f"config.jsonに不明な項目があります: {', '.join(sorted(unknown))}") from None
    missing_or_empty = [k for k in ("project_id", "project_name", "data_root")
                         if not isinstance(data.get(k), str) or not data[k].strip()]
    if missing_or_empty:
        raise RuntimeError(f"config.jsonの次の項目が未設定です: {', '.join(missing_or_empty)}") from None
    data["data_root"] = data["data_root"].strip()
    if not Path(data["data_root"]).is_absolute():
        raise RuntimeError(
            f"config.jsonのdata_rootは絶対パスで指定してください（現在の値: {data['data_root']}）。"
            "ローカルフォルダの例: \"C:\\\\KYデータ\"　／　NASの例: \"\\\\\\\\サーバー名\\\\共有名\\\\フォルダ\""
        ) from None
    storage_type = data.get("storage_type", "")
    if not isinstance(storage_type, str):
        raise RuntimeError("config.jsonのstorage_typeは文字列で指定してください（local または network）。") from None
    storage_type = storage_type.strip().lower()
    if storage_type and storage_type not in ("local", "network"):
        raise RuntimeError(f"config.jsonのstorage_typeはlocalまたはnetworkを指定してください（現在の値: {storage_type}）。") from None
    data["storage_type"] = storage_type
    return data


if CONFIG_FILE.is_file():
    PROJECT = _load_project_config(CONFIG_FILE)
elif getattr(sys, "frozen", False):
    raise RuntimeError(f"config.jsonが見つかりません（{CONFIG_FILE}）。EXEと同じフォルダにconfig.jsonを配置してください。") from None
if PROJECT:
    load_dotenv(APP_DIR / "secrets.env", override=True)
    key = os.getenv("VERTEX_API_KEY", "")
    if not key:
        raise RuntimeError(f"secrets.env（{APP_DIR / 'secrets.env'}）にVERTEX_API_KEYが設定されていません。") from None
    os.environ.setdefault("GEMINI_MODEL", "gemini-2.5-flash")
    os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "us-central1")
    os.environ["DATA_DIR"] = PROJECT["data_root"]
    os.environ["PHOTO_STORAGE_DIR"] = str(Path(PROJECT["data_root"]) / "images")
else:
    load_dotenv(BASE_DIR / ".env")


class Settings(BaseSettings):
    # Base Path (genba_safety_rag_app/)
    BASE_DIR: Path = BASE_DIR

    PROJECT_ID: str = PROJECT.get("project_id", "development")
    PROJECT_NAME: str = PROJECT.get("project_name", "開発用現場")
    STORAGE_TYPE: str = PROJECT.get("storage_type", "")

    # App Settings
    APP_NAME: str = "Genba Safety RAG App"
    DEBUG: bool = False
    
    # AI Settings
    # Single fixed provider/platform: Google Cloud Vertex AI (Gemini Flash).
    # Not user-selectable; kept as a constant so callers never hardcode the
    # string in multiple places.
    AI_PROVIDER: str = "vertex"
    VERTEX_API_KEY: str = ""
    GEMINI_MODEL: str = ""
    GOOGLE_CLOUD_PROJECT: str = ""
    GOOGLE_CLOUD_LOCATION: str = "us-central1"

    # Directory Paths
    STATIC_DIR: Path = BASE_DIR / "static"
    DATA_DIR: Path = BASE_DIR / "data"
    REFERENCE_PDF_DIR: Path = BASE_DIR / "reference_pdfs"  # 現状はルート直下
    HISTORY_DIR: Path = BASE_DIR / "history"            # 現状はルート直下
    # Shared history storage (per-record JSON files). Deployed via config.json's
    # data_root in production; this default is used only for local dev without
    # a config.json.
    PHOTO_STORAGE_DIR: Path = BASE_DIR / "data" / "photos"
    DEFAULT_CREATED_BY: str = ""

    model_config = SettingsConfigDict(
        env_file=None,
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @field_validator("DEBUG", mode="before")
    @classmethod
    def _normalize_debug_value(cls, value: object) -> object:
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"release", "prod", "production"}:
                return False
            if normalized in {"debug", "dev", "development"}:
                return True
        return value

settings = Settings()
