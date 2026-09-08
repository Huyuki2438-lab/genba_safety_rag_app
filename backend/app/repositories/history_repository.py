from __future__ import annotations
import json
import os
import threading
from datetime import datetime
from pathlib import Path
from uuid import UUID
from pydantic import BaseModel, ValidationError
from backend.app.core.config import settings
from backend.app.core.secrets import redact
from backend.app.core.shared_storage import HistoryStorageUnavailable, publish, require_root

class AnalysisHistoryRecord(BaseModel):
    id: str
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None
    created_by: str = ""
    site_name: str = ""
    work_content: str = ""
    main_risk: str = ""
    image_name: str
    image_mime_type: str = "image/jpeg"
    photo_relative_path: str
    mode: str
    provider_display_label: str
    model: str
    markdown: str

class HistoryRepository:
    def __init__(self, root: Path | None = None, project_id: str | None = None):
        self.root = root or settings.DATA_DIR
        self.project_id = project_id or settings.PROJECT_ID
        self._cache = {}
        self._lock = threading.RLock()

    def initialize_schema(self):
        require_root(self.root)
        for folder in ("records", "images", "reports", "export"):
            (self.root / folder).mkdir(exist_ok=True)

    def _files(self):
        require_root(self.root / "records")
        def failed(error):
            raise error
        try:
            return [Path(base) / name for base, _, names in os.walk(self.root / "records", onerror=failed)
                    for name in names if name.endswith(".json")]
        except OSError:
            raise HistoryStorageUnavailable("共有履歴を読み込めません。NASの接続と読み取り権限を確認してください。") from None

    def _read(self, path):
        try:
            stat = path.stat()
            stamp = (stat.st_mtime_ns, stat.st_size)
            with self._lock:
                cached = self._cache.get(path)
            if cached and cached[0] == stamp:
                return cached[1]
            raw = json.loads(path.read_text(encoding="utf-8"))
            if raw.get("schema_version") != 1 or raw.get("project_id") != self.project_id:
                return None
            record = AnalysisHistoryRecord.model_validate(redact(raw["analysis"]))
            if str(UUID(record.id)) != raw.get("record_id") or path.stem != record.id:
                raise ValueError()
            if not record.created_at.tzinfo or not record.updated_at.tzinfo:
                raise ValueError()
            relative = Path(record.photo_relative_path)
            if relative.is_absolute() or ".." in relative.parts or ":" in str(relative) or record.mode not in settings.TARGETS:
                raise ValueError()
        except (ValueError, KeyError, TypeError, AttributeError, ValidationError):
            record = None
        except OSError:
            raise HistoryStorageUnavailable("共有履歴を読み込めません。NASの接続と読み取り権限を確認してください。") from None
        with self._lock:
            self._cache[path] = (stamp, record)
        return record

    def list(self, *, created_from=None, created_to=None, site_name=None, work_content=None, created_by=None, keyword=None):
        result = []
        files = self._files()
        for path in files:
            record = self._read(path)
            if record is None or record.deleted_at or path.with_suffix(".deleted").exists():
                continue
            if created_from and record.created_at < created_from:
                continue
            if created_to and record.created_at >= created_to:
                continue
            if any(value and value.casefold() not in getattr(record, field).casefold()
                   for field, value in (("site_name", site_name), ("work_content", work_content), ("created_by", created_by))):
                continue
            if keyword and keyword.casefold() not in " ".join((record.site_name, record.work_content, record.main_risk, record.markdown, record.image_name)).casefold():
                continue
            result.append(record)
        with self._lock:
            live = set(files)
            self._cache = {p: v for p, v in self._cache.items() if p in live}
        return sorted(result, key=lambda r: (r.created_at, r.id), reverse=True)

    def _path(self, entry_id):
        try:
            entry_id = str(UUID(entry_id))
        except ValueError:
            return None
        return next((p for p in self._files() if p.stem == entry_id), None)

    def get_any(self, entry_id):
        path = self._path(entry_id)
        return self._read(path) if path else None

    def get(self, entry_id):
        path = self._path(entry_id)
        if not path or path.with_suffix(".deleted").exists():
            return None
        record = self._read(path)
        return record if record and not record.deleted_at else None

    def add(self, record):
        require_root(self.root / "records")
        record = AnalysisHistoryRecord.model_validate(redact(record.model_dump()))
        UUID(record.id)
        payload = dict(schema_version=1, record_id=record.id, project_id=self.project_id,
                       created_at=record.created_at.isoformat(), analysis=record.model_dump(mode="json"))
        path = self.root / "records" / record.created_at.strftime("%Y-%m") / f"{record.id}.json"
        publish(path, json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"))
        return record

    def soft_delete(self, entry_id, deleted_at):
        path = self._path(entry_id)
        if not path or not self._read(path):
            return False
        marker = path.with_suffix(".deleted")
        if marker.exists():
            return True
        try:
            publish(marker, deleted_at.isoformat().encode())
        except HistoryStorageUnavailable:
            if not marker.exists():
                raise
        return True

history_repository = HistoryRepository()
