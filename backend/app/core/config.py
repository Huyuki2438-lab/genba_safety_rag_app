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


class _ConfigReadIOError(RuntimeError):
    """config.json自体は存在するがOSレベルで読み取れない(一過性の可能性あり)。"""


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

    data_root が未設定(空文字)のconfig.jsonは、初回起動の「初期設定」画面で
    保存先を選ぶまでの一時状態として許容する(ユーザーにJSON手編集させないため)。
    その場合はproject_id・project_nameも未設定のままでよい。data_rootが設定
    済みの場合のみ、従来どおりproject_id・project_nameの必須チェックを行う。
    """
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        # onefile化したEXEは起動のたびに同梱データを一時フォルダへ展開するため、
        # 展開が完了する前の一瞬だけ読み取りが失敗することがある(ウイルス対策
        # ソフトのスキャン等)。この種の一過性I/Oエラーは「保存先未設定」として
        # 握り潰さず、desktop_app.py側のリトライで再試行できるよう素通しする。
        raise _ConfigReadIOError(f"config.jsonを読み込めません（{path}）。ファイルの存在とアクセス権限を確認してください。詳細: {exc}") from exc
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
    for key in ("project_id", "project_name", "data_root", "storage_type"):
        if key in data and not isinstance(data[key], str):
            raise RuntimeError(f"config.jsonの{key}は文字列で指定してください。") from None
        data[key] = data.get(key, "").strip()
    data_root = data["data_root"]
    if data_root:
        missing_or_empty = [k for k in ("project_id", "project_name") if not data[k]]
        if missing_or_empty:
            raise RuntimeError(f"config.jsonの次の項目が未設定です: {', '.join(missing_or_empty)}") from None
        if not Path(data_root).is_absolute():
            raise RuntimeError(
                f"config.jsonのdata_rootは絶対パスで指定してください（現在の値: {data_root}）。"
                "ローカルフォルダの例: \"C:\\\\KYデータ\"　／　NASの例: \"\\\\\\\\サーバー名\\\\共有名\\\\フォルダ\""
            ) from None
    storage_type = data["storage_type"].lower()
    if storage_type and storage_type not in ("local", "network"):
        raise RuntimeError(f"config.jsonのstorage_typeはlocalまたはnetworkを指定してください（現在の値: {storage_type}）。") from None
    data["storage_type"] = storage_type
    return data


SETUP_CONFIG_ERROR: str | None = None
_PROJECT_RAW: dict = {}
if CONFIG_FILE.is_file():
    try:
        _PROJECT_RAW = _load_project_config(CONFIG_FILE)
    except _ConfigReadIOError:
        # 一過性の可能性があるI/Oエラーはここで握り潰さず、呼び出し元
        # (desktop_app.pyの起動リトライ)まで伝播させる。
        raise
    except RuntimeError as exc:
        # 内容が壊れたconfig.json(JSON構文エラー・必須項目欠落等)は、
        # アプリを異常終了させず初期設定画面へ誘導する。
        SETUP_CONFIG_ERROR = str(exc)
        _PROJECT_RAW = {}

DATA_ROOT_CONFIGURED = bool(_PROJECT_RAW.get("data_root"))
# 開発時(.envのみでの起動)は従来どおり初期設定画面を出さない。exe化(frozen)時、
# またはテスト等でKY_CONFIG_FILEを明示指定した場合のみ初期設定フローの対象とする。
SETUP_REQUIRED = not DATA_ROOT_CONFIGURED and (getattr(sys, "frozen", False) or "KY_CONFIG_FILE" in os.environ)
PROJECT = _PROJECT_RAW if DATA_ROOT_CONFIGURED else {}
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

    # データ保存先が未設定で「初期設定」画面を表示する必要があるか。
    SETUP_REQUIRED: bool = SETUP_REQUIRED
    CONFIG_FILE: Path = CONFIG_FILE

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
