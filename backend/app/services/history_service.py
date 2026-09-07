from __future__ import annotations

import base64
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo

from backend.app.repositories.history_repository import HistoryRepository, HISTORY_LIMIT
from backend.app.schemas.history import AnalysisHistoryEntry

try:
    JST = ZoneInfo("Asia/Tokyo")
except Exception:
    # Windows 環境などで tzdata が未導入でも JST を維持する。
    JST = timezone(timedelta(hours=9), name="Asia/Tokyo")

_REIWA_LABEL = "令和"
_GAN_LABEL = "元"
_YEAR_LABEL = "年"
_MONTH_LABEL = "月"
_DAY_LABEL = "日"
_HOUR_LABEL = "時"
_MINUTE_LABEL = "分"
_SECOND_LABEL = "秒"


# ---------------------------------------------------------------------------
# 日付ユーティリティ
# ---------------------------------------------------------------------------

def _parse_created_at(value: str) -> datetime:
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return datetime.now(JST)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=JST)
    return parsed.astimezone(JST)


def _to_reiwa_label(dt: datetime) -> str:
    if dt.date() < date(2019, 5, 1):
        era_year_text = _GAN_LABEL
    else:
        era_year = dt.year - 2018
        era_year_text = _GAN_LABEL if era_year <= 1 else str(era_year)

    return (
        f"{_REIWA_LABEL}{era_year_text}{_YEAR_LABEL}"
        f"{dt.month:02d}{_MONTH_LABEL}{dt.day:02d}{_DAY_LABEL}"
        f"{dt.hour:02d}{_HOUR_LABEL}{dt.minute:02d}{_MINUTE_LABEL}{dt.second:02d}{_SECOND_LABEL}"
    )


# ---------------------------------------------------------------------------
# フォルダ名・ファイル名ユーティリティ
# ---------------------------------------------------------------------------

def _safe_segment(value: str, fallback: str) -> str:
    normalized = re.sub(r"[\\/:*?\"<>|]", "_", value).strip().strip(".")
    return normalized or fallback


def _default_history_folder(entry: AnalysisHistoryEntry) -> str:
    created_at = _parse_created_at(entry.createdAt)
    id_suffix = _safe_segment(entry.id, "entry")[-8:]
    return f"{_to_reiwa_label(created_at)}_{id_suffix}"


def _resolve_entry_folder_name(entry: AnalysisHistoryEntry) -> str:
    requested = (entry.historyFolder or "").strip()
    return (
        _safe_segment(requested, _default_history_folder(entry))
        if requested
        else _default_history_folder(entry)
    )


def _guess_image_extension(image_name: str, image_mime_type: str | None) -> str:
    suffix = Path(image_name).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".svg"}:
        return suffix
    mime_to_ext = {
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
        "image/bmp": ".bmp",
        "image/svg+xml": ".svg",
    }
    if image_mime_type:
        return mime_to_ext.get(image_mime_type.lower(), ".jpg")
    return ".jpg"


def _build_image_url(folder_name: str, image_file_name: str | None) -> str | None:
    if not image_file_name:
        return None
    encoded_folder = quote(folder_name, safe="")
    encoded_file = quote(image_file_name, safe="")
    return f"/history/{encoded_folder}/{encoded_file}"


# ---------------------------------------------------------------------------
# HistoryService（ビジネスロジック専任）
# ---------------------------------------------------------------------------

class HistoryService:
    def __init__(self, repository: HistoryRepository | None = None):
        self._repo = repository or HistoryRepository()

    def _save_entry_image(self, entry: AnalysisHistoryEntry, folder_path: Path) -> str | None:
        image_base64 = (entry.imageBase64 or "").strip()
        if not image_base64:
            file_name = (entry.imageFileName or "").strip()
            if file_name and (folder_path / file_name).is_file():
                return file_name
            return None

        try:
            image_bytes = base64.b64decode(image_base64, validate=True)
        except Exception:
            return None

        stem = _safe_segment(Path(entry.imageName).stem, "photo")
        ext = _guess_image_extension(entry.imageName, entry.imageMimeType)
        file_name = f"{stem}{ext}"
        (folder_path / file_name).write_bytes(image_bytes)
        return file_name

    def _hydrate_entry(self, entry: AnalysisHistoryEntry) -> AnalysisHistoryEntry:
        folder_name = (entry.historyFolder or "").strip()
        image_file_name = (entry.imageFileName or "").strip() or None
        image_url = entry.imageUrl
        if folder_name:
            image_url = _build_image_url(folder_name, image_file_name)
        return entry.model_copy(
            update={
                "historyFolder": folder_name or None,
                "imageFileName": image_file_name,
                "imageUrl": image_url,
                "imageBase64": None,
            }
        )

    def load_analysis_history(self) -> list[AnalysisHistoryEntry]:
        entries = self._repo.load()
        return [self._hydrate_entry(e) for e in entries]

    def save_analysis_history(self, entries: list[AnalysisHistoryEntry]) -> list[AnalysisHistoryEntry]:
        normalized = entries[:HISTORY_LIMIT]
        persisted: list[AnalysisHistoryEntry] = []

        with self._repo.lock:
            self._repo.ensure_dir()

            for raw_entry in normalized:
                folder_name = _resolve_entry_folder_name(raw_entry)
                folder_path = self._repo.resolve_folder(folder_name)
                image_file_name = self._save_entry_image(raw_entry, folder_path)
                image_url = _build_image_url(folder_name, image_file_name)

                persisted_entry = raw_entry.model_copy(
                    update={
                        "historyFolder": folder_name,
                        "imageFileName": image_file_name,
                        "imageUrl": image_url,
                        "imageBase64": None,
                    }
                )
                detail_payload = persisted_entry.model_dump(exclude={"imageBase64"})
                self._repo.save_entry_detail(folder_path, detail_payload)
                persisted.append(persisted_entry)

            self._repo.save(persisted)

        return persisted


# シングルトンインスタンス
history_service = HistoryService()


# ---------------------------------------------------------------------------
# 後方互換ラッパー（history.py から呼ぶ関数）
# ---------------------------------------------------------------------------

def load_analysis_history() -> list[AnalysisHistoryEntry]:
    return history_service.load_analysis_history()


def save_analysis_history(entries: list[AnalysisHistoryEntry]) -> list[AnalysisHistoryEntry]:
    return history_service.save_analysis_history(entries)
