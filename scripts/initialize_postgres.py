"""Compatibility entry point: create data subfolders only; no database is used."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.repositories.history_repository import history_repository

if __name__ == "__main__":
    history_repository.initialize_schema()
    print("Shared JSON data directories initialized (no database)")
