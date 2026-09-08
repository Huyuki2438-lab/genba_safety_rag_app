from __future__ import annotations

import base64
import json
import os
import re
import uuid
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo

from backend.app.core.config import settings
from backend.app.core.shared_storage import publish, require_root
from backend.app.repositories.history_repository import AnalysisHistoryRecord, HistoryRepository, HistoryStorageUnavailable, history_repository
from backend.app.schemas.history import AnalysisHistoryEntry, CreateAnalysisHistoryRequest

try:
    JST = ZoneInfo("Asia/Tokyo")
except Exception:
    JST = timezone(timedelta(hours=9), name="Asia/Tokyo")


def _safe_filename(value: str) -> str:
    return re.sub(r"[\\/:*?\"<>|]", "_", value).strip().strip(".") or "photo"


def _extension(image_name: str, mime_type: str | None) -> str:
    suffix = Path(image_name).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}:
        return suffix
    return {"image/png": ".png", "image/webp": ".webp", "image/gif": ".gif", "image/bmp": ".bmp"}.get((mime_type or "").lower(), ".jpg")


def _entry_from_record(record: AnalysisHistoryRecord) -> AnalysisHistoryEntry:
    relative_url = "/history/" + quote(record.photo_relative_path.replace("\\", "/"), safe="/")
    return AnalysisHistoryEntry(
        id=record.id, createdAt=record.created_at, updatedAt=record.updated_at,
        createdBy=record.created_by, siteName=record.site_name, workContent=record.work_content,
        mainRisk=record.main_risk, imageName=record.image_name, imageMimeType=record.image_mime_type,
        imageUrl=relative_url, mode=record.mode, providerDisplayLabel=record.provider_display_label,
        model=record.model, markdown=record.markdown,
    )


class HistoryService:
    def __init__(self, repository: HistoryRepository | None = None):
        self._repo = repository or history_repository

    def list(self, *, date_from: date | None = None, date_to: date | None = None, site_name: str | None = None,
             work_content: str | None = None, created_by: str | None = None, keyword: str | None = None, offset: int = 0, limit: int = 50) -> list[AnalysisHistoryEntry]:
        self._assert_photo_storage()
        created_from = datetime.combine(date_from, time.min, tzinfo=JST) if date_from else None
        created_to = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=JST) if date_to else None
        return [_entry_from_record(record) for record in self._repo.list(
            created_from=created_from, created_to=created_to, site_name=site_name,
            work_content=work_content, created_by=created_by, keyword=keyword,
        )[offset:offset + limit]]

    def get(self, entry_id: str) -> AnalysisHistoryEntry | None:
        self._assert_photo_storage()
        record = self._repo.get(entry_id)
        return _entry_from_record(record) if record else None

    def create(self, request: CreateAnalysisHistoryRequest, *, fallback_created_by: str) -> AnalysisHistoryEntry:
        try:
            image_bytes = base64.b64decode(request.imageBase64, validate=True)
        except Exception as exc:
            raise ValueError("写真データを読み込めませんでした。") from exc
        if not image_bytes:
            raise ValueError("写真データが空です。")
        require_root(settings.DATA_DIR / "records")
        require_root(settings.PHOTO_STORAGE_DIR)
        now = datetime.now(JST)
        entry_id = str(uuid.uuid4())
        relative_path = Path(f"{now:%Y}") / f"{now:%m}" / f"{entry_id}{_extension(request.imageName, request.imageMimeType)}"
        destination = settings.PHOTO_STORAGE_DIR / relative_path
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            publish(destination, image_bytes)
        except OSError as exc:
            raise OSError("共有写真ストレージへ保存できませんでした。") from exc
        try:
            record = AnalysisHistoryRecord(
                id=entry_id, created_at=now, updated_at=now, deleted_at=None,
                created_by=(request.createdBy.strip() or fallback_created_by or "不明")[:255],
                site_name=request.siteName.strip(), work_content=request.workContent.strip(), main_risk=request.mainRisk.strip(),
                image_name=_safe_filename(request.imageName)[:500], image_mime_type=(request.imageMimeType or "image/jpeg")[:100],
                photo_relative_path=relative_path.as_posix(), mode=request.mode,
                provider_display_label=request.providerDisplayLabel, model=request.model, markdown=request.markdown,
            )
            return _entry_from_record(self._repo.add(record))
        except Exception:
            # A lost SMB acknowledgement may mean the record was committed.
            # Retain its photo; removing it here could corrupt committed data.
            raise

    def soft_delete(self, entry_id: str) -> bool:
        self._assert_photo_storage()
        return self._repo.soft_delete(entry_id, datetime.now(JST))

    def import_legacy_folder(self, source_dir: Path) -> tuple[int, int]:
        """Import the previous JSON/file history layout into common storage.

        The operation is idempotent: a deterministic UUID is derived from the
        source directory and old entry id, so an already imported entry is
        skipped on subsequent runs.
        """
        require_root(settings.DATA_DIR / "records")
        require_root(settings.PHOTO_STORAGE_DIR)
        index_file = source_dir / "analysis_history.json"
        try:
            raw_entries = json.loads(index_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"旧履歴ファイルを読み込めません: {index_file}") from exc
        if not isinstance(raw_entries, list):
            raise ValueError(f"旧履歴ファイルの形式が不正です: {index_file}")

        imported = skipped = 0
        for raw in raw_entries:
            if not isinstance(raw, dict):
                skipped += 1
                continue
            old_id = str(raw.get("id") or "")
            if not old_id:
                skipped += 1
                continue
            entry_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{source_dir.resolve()}|{old_id}"))
            if self._repo.get_any(entry_id):
                skipped += 1
                continue
            folder_name = str(raw.get("historyFolder") or "")
            image_file_name = str(raw.get("imageFileName") or "")
            source_image = source_dir / folder_name / image_file_name
            if not source_image.resolve().is_relative_to(source_dir.resolve()) or not folder_name or not image_file_name or not source_image.is_file():
                skipped += 1
                continue
            try:
                created_at = _legacy_datetime(str(raw.get("createdAt") or ""))
                extension = _extension(str(raw.get("imageName") or image_file_name), raw.get("imageMimeType"))
                relative_path = Path(f"{created_at:%Y}") / f"{created_at:%m}" / f"{uuid.uuid4()}{extension}"
                destination = settings.PHOTO_STORAGE_DIR / relative_path
                destination.parent.mkdir(parents=True, exist_ok=True)
                publish(destination, source_image.read_bytes())
                mode = raw.get("mode") if raw.get("mode") in {"gemini_a", "gemini_b", "vertex"} else "gemini_a"
                record = AnalysisHistoryRecord(
                    id=entry_id, created_at=created_at, updated_at=created_at, deleted_at=None,
                    created_by="旧履歴取込", site_name="", work_content="", main_risk="",
                    image_name=_safe_filename(str(raw.get("imageName") or image_file_name))[:500],
                    image_mime_type=str(raw.get("imageMimeType") or "image/jpeg")[:100],
                    photo_relative_path=relative_path.as_posix(), mode=mode,
                    provider_display_label=str(raw.get("providerDisplayLabel") or "KY")[:255],
                    model=str(raw.get("model") or "旧履歴")[:255], markdown=str(raw.get("markdown") or ""),
                )
                self._repo.add(record)
                imported += 1
            except (OSError, ValueError, HistoryStorageUnavailable):
                # Retain photos if a commit acknowledgement was lost.
                skipped += 1
        return imported, skipped

    @staticmethod
    def _assert_photo_storage() -> None:
        require_root(settings.PHOTO_STORAGE_DIR)



def _legacy_datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(JST)
    return parsed.replace(tzinfo=JST) if parsed.tzinfo is None else parsed.astimezone(JST)


history_service = HistoryService()
