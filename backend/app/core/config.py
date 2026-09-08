from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Literal
from dotenv import load_dotenv

from pydantic import BaseModel, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _compute_base_dir() -> Path:
    """アプリの基準ディレクトリを求める。

    PyInstaller (onedir) でexe化した場合、__file__ はビルド内部の展開先を
    指してしまうため、実際にexeが置かれているフォルダ(ネットワーク共有上の
    UNCパス等も含む)を基準にする必要がある。
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent.parent.parent


# Base Path を計算
BASE_DIR = _compute_base_dir()

# .env を明示的に読み込んで os.environ に展開
load_dotenv(BASE_DIR / ".env")

TargetKind = Literal["gemini", "vertex"]


class TargetConfig(BaseModel):
    label: str
    kind: TargetKind
    api_key_env: str
    model_env: str
    project_id_env: str | None = None
    location_env: str | None = None

    model_config = {
        "protected_namespaces": ()
    }

    def get_api_key(self) -> str:
        return os.getenv(self.api_key_env, "")

    def get_model(self) -> str:
        return os.getenv(self.model_env, "")

    def get_project_id(self) -> str | None:
        return os.getenv(self.project_id_env) if self.project_id_env else None

    def get_location(self) -> str | None:
        return os.getenv(self.location_env) if self.location_env else None


class Settings(BaseSettings):
    # Base Path (genba_safety_rag_app/)
    BASE_DIR: Path = BASE_DIR

    # App Settings
    APP_NAME: str = "Genba Safety RAG App"
    DEBUG: bool = False
    
    # AI Settings
    DEFAULT_AI_TARGET: str = "gemini_a"

    # Directory Paths
    STATIC_DIR: Path = BASE_DIR / "static"
    DATA_DIR: Path = BASE_DIR / "data"
    REFERENCE_PDF_DIR: Path = BASE_DIR / "reference_pdfs"  # 現状はルート直下
    HISTORY_DIR: Path = BASE_DIR / "history"            # 現状はルート直下
    # Shared history storage. These values are deployed in the company .env.
    DATABASE_URL: str = ""
    PHOTO_STORAGE_DIR: Path = BASE_DIR / "data" / "photos"
    DEFAULT_CREATED_BY: str = ""

    # AI Target Configuration (Static for now, could be moved to json/yaml)
    TARGETS: dict[str, TargetConfig] = {
        "gemini_a": TargetConfig(
            label="KY",
            kind="gemini",
            api_key_env="GEMINI_A_API_KEY",
            model_env="GEMINI_A_MODEL",
        ),
        "gemini_b": TargetConfig(
            label="KY予備",
            kind="gemini",
            api_key_env="GEMINI_B_API_KEY",
            model_env="GEMINI_B_MODEL",
        ),
        "vertex": TargetConfig(
            label="VERTEX",
            kind="vertex",
            api_key_env="VERTEX_API_KEY",
            model_env="VERTEX_MODEL",
            project_id_env="VERTEX_PROJECT_ID",
            location_env="VERTEX_LOCATION",
        ),
    }

    model_config = SettingsConfigDict(
        env_file=".env",
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
