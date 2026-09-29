from __future__ import annotations
import json
import logging
import os
import threading
from datetime import datetime
from pathlib import Path
from uuid import UUID
from pydantic import BaseModel, ValidationError
from backend.app.core.config import settings
from backend.app.core.secrets import redact
from backend.app.core.shared_storage import HistoryStorageUnavailable, _describe, _guidance, check_writable, publish, require_root

logger = logging.getLogger("genba_safety_rag_app.history")

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
        try:
            for folder in ("records", "images", "reports", "export"):
                (self.root / folder).mkdir(exist_ok=True)
        except OSError as exc:
            raise HistoryStorageUnavailable(
                f"{_describe(self.root)}にフォルダを作成できません（{self.root}）。{_guidance(self.root)} 詳細: {exc}"
            ) from None
        check_writable(self.root / "records")

    def _scan(self):
        """records配下を再帰的に走査し、(パス, statの結果, .deletedマーカー一覧)を返す。

        os.scandirのDirEntryが持つstat情報をそのまま使うことで、NAS越しに
        ファイルごとへ改めてstat()する分の往復(list()呼び出しのたびに件数分
        発生していた)を省く。.deletedマーカーの有無も同じ走査結果から判定できる
        ようにし、record毎に別途exists()する往復も省く。全件を毎回列挙する点は
        変えていないため、他PC/他プロセスによる変更が即座に反映される既存の
        整合性は保つ。
        """
        require_root(self.root / "records")
        files = []
        deleted_markers = set()
        def walk(directory):
            try:
                with os.scandir(directory) as entries:
                    for entry in entries:
                        if entry.is_dir(follow_symlinks=False):
                            walk(entry.path)
                        elif entry.name.endswith(".json"):
                            files.append((Path(entry.path), entry.stat(follow_symlinks=False)))
                        elif entry.name.endswith(".deleted"):
                            deleted_markers.add(Path(entry.path))
            except OSError as exc:
                raise HistoryStorageUnavailable("共有履歴を読み込めません。NASの接続と読み取り権限を確認してください。") from exc
        walk(self.root / "records")
        return files, deleted_markers

    def _files(self):
        files, _ = self._scan()
        return [path for path, _ in files]

    def _read(self, path, stat=None):
        try:
            if stat is None:
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
            if relative.is_absolute() or ".." in relative.parts or ":" in str(relative) or not record.mode:
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
        files, deleted_markers = self._scan()
        for path, stat in files:
            record = self._read(path, stat)
            if record is None or record.deleted_at or path.with_suffix(".deleted") in deleted_markers:
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
            live = {path for path, _ in files}
            self._cache = {p: v for p, v in self._cache.items() if p in live}
        if not result and files:
            self._warn_if_project_mismatch([path for path, _ in files])
        return sorted(result, key=lambda r: (r.created_at, r.id), reverse=True)

    def _warn_if_project_mismatch(self, files):
        """履歴が0件のとき、project_idの不一致が原因かをログへ残す。"""
        foreign_ids = set()
        for path in files[:50]:
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            project_id = raw.get("project_id")
            if project_id and project_id != self.project_id:
                foreign_ids.add(project_id)
        if foreign_ids:
            logger.warning(
                "履歴が0件です。data_root(%s)内に別のproject_id(%s)の履歴ファイルがあります。"
                "現在のconfig.jsonのproject_id=%sが正しいか、data_rootが想定の現場フォルダを指しているか確認してください。",
                self.root, ", ".join(sorted(foreign_ids)), self.project_id,
            )

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
