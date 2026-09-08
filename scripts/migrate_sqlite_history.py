"""Developer migration: read-only SQLite snapshot -> immutable per-record files.
Usage: set KY_CONFIG_FILE to the target config, then pass a LOCAL database backup
and the old photos directory. Close all old applications before taking the backup.
No database on NAS is opened or updated by this tool.
"""
import argparse
import sqlite3
import sys
from pathlib import Path
from uuid import UUID, uuid4
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.core.config import settings
from backend.app.core.shared_storage import require_root, publish
from backend.app.repositories.history_repository import history_repository, AnalysisHistoryRecord
from backend.app.services.history_service import _legacy_datetime

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("database", type=Path)
    parser.add_argument("photos", type=Path)
    args = parser.parse_args()
    source = args.database.resolve()
    if str(source).startswith("\\\\"):
        raise SystemExit("Use a local backup of the old SQLite database")
    require_root(settings.DATA_DIR / "records")
    require_root(settings.PHOTO_STORAGE_DIR)
    db = sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    imported = skipped = 0
    try:
        for row in db.execute("SELECT * FROM ky_analysis_history"):
            raw = dict(row)
            entry_id = str(UUID(raw["id"]))
            if history_repository.get_any(entry_id):
                skipped += 1
                continue
            photo = (args.photos / raw["photo_relative_path"]).resolve()
            if not photo.is_relative_to(args.photos.resolve()) or not photo.is_file():
                raise ValueError("Missing or invalid source photo; no records are removed")
            suffix = photo.suffix.lower()
            if suffix not in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}:
                raise ValueError("Unsupported photo type")
            relative = Path("migrated") / f"{uuid4()}{suffix}"
            publish(settings.PHOTO_STORAGE_DIR / relative, photo.read_bytes())
            raw["photo_relative_path"] = relative.as_posix()
            for name in ("created_at", "updated_at", "deleted_at"):
                raw[name] = _legacy_datetime(raw[name]) if raw[name] else None
            history_repository.add(AnalysisHistoryRecord.model_validate(raw))
            imported += 1
    finally:
        db.close()
    print(f"Imported: {imported}; already present: {skipped}. Source unchanged.")
if __name__ == "__main__":
    main()
