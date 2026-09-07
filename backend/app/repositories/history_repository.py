from __future__ import annotations

import json
import threading
from pathlib import Path

from backend.app.core.config import settings
from backend.app.schemas.history import AnalysisHistoryEntry

HISTORY_LIMIT = 20
ENTRY_DETAIL_FILE = "analysis.json"

_history_lock = threading.Lock()


class HistoryRepository:
    """履歴データのファイルIO専任クラス。"""

    @property
    def _history_dir(self) -> Path:
        return settings.HISTORY_DIR

    @property
    def _history_file(self) -> Path:
        return self._history_dir / "analysis_history.json"

    def ensure_dir(self) -> None:
        self._history_dir.mkdir(parents=True, exist_ok=True)

    def load(self) -> list[AnalysisHistoryEntry]:
        with _history_lock:
            self.ensure_dir()
            if not self._history_file.exists():
                return []

            try:
                raw = self._history_file.read_text(encoding="utf-8")
                data = json.loads(raw)
            except (OSError, json.JSONDecodeError):
                return []

            if not isinstance(data, list):
                return []

            parsed: list[AnalysisHistoryEntry] = []
            for item in data:
                try:
                    parsed.append(AnalysisHistoryEntry.model_validate(item))
                except Exception:
                    continue

            return parsed[:HISTORY_LIMIT]

    def save(self, entries: list[AnalysisHistoryEntry]) -> None:
        self.ensure_dir()
        payload = [
            entry.model_dump(exclude={"imageBase64"})
            for entry in entries
        ][:HISTORY_LIMIT]
        temp_file = self._history_file.with_suffix(".tmp")
        temp_file.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temp_file.replace(self._history_file)

    def save_entry_detail(self, folder_path: Path, payload: dict) -> None:
        detail_file = folder_path / ENTRY_DETAIL_FILE
        temp_file = folder_path / f"{ENTRY_DETAIL_FILE}.tmp"
        temp_file.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temp_file.replace(detail_file)

    def resolve_folder(self, folder_name: str) -> Path:
        folder_path = self._history_dir / folder_name
        folder_path.mkdir(parents=True, exist_ok=True)
        return folder_path

    @property
    def lock(self) -> threading.Lock:
        return _history_lock
