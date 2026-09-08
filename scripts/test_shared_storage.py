"""Regression tests: no network, no real keys, no changes to production data."""
import base64
import json
import os
import sys
import tempfile
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.core.config import settings
from backend.app.core.shared_storage import publish, HistoryStorageUnavailable
from backend.app.repositories.history_repository import HistoryRepository, AnalysisHistoryRecord
from backend.app.services.history_service import HistoryService
from backend.app.schemas.history import CreateAnalysisHistoryRequest


def record():
    return AnalysisHistoryRecord(id=str(uuid.uuid4()), created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
        image_name="写真.png", photo_relative_path="2026/09/photo.png", mode="gemini_a", provider_display_label="KY",
        model="test", markdown="危険：重機接触\n対策：立入禁止", site_name="試験現場")


def write_batch(root, count):
    repo = HistoryRepository(Path(root), "001")
    for _ in range(count):
        repo.add(record())
    return count


class SharedStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="KY 日本語 空白 ")
        self.root = Path(self.temp.name)
        self.repo = HistoryRepository(self.root, "001")
        self.repo.initialize_schema()
    def tearDown(self):
        self.temp.cleanup()
    def test_two_processes_concurrent_publication(self):
        with ProcessPoolExecutor(2) as pool:
            self.assertEqual(sum(pool.map(write_batch, [str(self.root)] * 2, [35, 35])), 70)
        other_pc = HistoryRepository(self.root, "001")
        self.assertEqual(len(other_pc.list()), 70)
        self.assertEqual(len({r.id for r in other_pc.list()}), 70)
        self.assertEqual(len(list(self.root.rglob("*.uploading"))), 0)
    def test_partial_corrupt_foreign_and_future_are_skipped(self):
        item = self.repo.add(record())
        folder = self.root / "records"
        (folder / "partial.uploading").write_text('{')
        (folder / "corrupt.json").write_text('{')
        (folder / "future.json").write_text('{"schema_version": 9}')
        self.assertEqual([r.id for r in self.repo.list()], [item.id])
        self.assertEqual(HistoryRepository(self.root, "002").list(), [])
    def test_disconnect_reconnect_no_fallback(self):
        self.repo.add(record())
        folder = self.root / "records"
        folder.rename(self.root / "offline")
        with self.assertRaises(HistoryStorageUnavailable): self.repo.list()
        self.assertFalse(folder.exists())
        (self.root / "offline").rename(folder)
        self.assertEqual(len(self.repo.list()), 1)
    def test_write_failure_and_collision_preserve_existing(self):
        target = self.root / "records" / "unique.json"
        publish(target, b"original")
        with self.assertRaises(HistoryStorageUnavailable): publish(target, b"replacement")
        self.assertEqual(target.read_bytes(), b"original")
        for error in (PermissionError(), OSError(28, "disk full"), OSError(64, "network disconnected")):
            with patch("backend.app.core.shared_storage.os.rename", side_effect=error):
                with self.assertRaises(HistoryStorageUnavailable): publish(self.root / "records" / "failed.json", b"data")
        self.assertFalse((self.root / "records" / "failed.json").exists())
        self.assertFalse(list(self.root.rglob("*.uploading")))
    def test_read_permission_errors_reported(self):
        self.repo.add(record())
        with patch("pathlib.Path.read_text", side_effect=PermissionError()):
            with self.assertRaises(HistoryStorageUnavailable): self.repo.list()
    def test_concurrent_deletes_immutable_record(self):
        item = self.repo.add(record())
        original = next(self.root.rglob("*.json")).read_bytes()
        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(lambda _: self.repo.soft_delete(item.id, datetime.now(timezone.utc)), range(2)))
        self.assertTrue(all(results))
        self.assertIsNone(HistoryRepository(self.root, "001").get(item.id))
        self.assertEqual(next(self.root.rglob("*.json")).read_bytes(), original)
    def test_missing_photo_does_not_hide_text(self):
        item = self.repo.add(record())
        self.assertEqual(self.repo.get(item.id).markdown, item.markdown)
    def test_file_updates_revalidate_cache(self):
        self.repo.add(record()); self.assertEqual(len(self.repo.list()), 1)
        next(self.root.rglob("*.json")).write_text("broken")
        self.assertEqual(self.repo.list(), [])
    def test_acknowledgement_loss_keeps_photo(self):
        request = CreateAnalysisHistoryRequest(imageName="a.png", imageBase64=base64.b64encode(b"photo").decode(),
            mode="gemini_a", providerDisplayLabel="KY", model="test", markdown="result")
        with patch.object(settings, "DATA_DIR", self.root), patch.object(settings, "PHOTO_STORAGE_DIR", self.root / "images"):
            with patch.object(self.repo, "add", side_effect=HistoryStorageUnavailable("lost acknowledgement")):
                with self.assertRaises(HistoryStorageUnavailable): HistoryService(self.repo).create(request, fallback_created_by="test")
        self.assertEqual(len(list((self.root / "images").rglob("*.jpg"))), 0)
        self.assertEqual(len(list((self.root / "images").rglob("*.png"))), 1)
    def test_known_secret_redacted_from_records(self):
        secret = "test-secret-never-persist-123456789"
        with patch.dict(os.environ, {"GEMINI_API_KEY": secret}):
            item = record(); item.markdown = "結果 " + secret
            self.repo.add(item)
            self.assertNotIn(secret, next(self.root.rglob("*.json")).read_text(encoding="utf-8"))
            self.assertNotIn(secret, self.repo.get(item.id).markdown)
    def test_invalid_target_and_path_record_skipped(self):
        item = record(); item.photo_relative_path = "../../secrets.env"
        self.repo.add(item)
        self.assertEqual(self.repo.list(), [])
    def test_thousands_filter_and_page(self):
        for _ in range(1000): self.repo.add(record())
        with patch.object(settings, "PHOTO_STORAGE_DIR", self.root / "images"):
            service = HistoryService(self.repo)
            first = service.list(limit=50)
            second = service.list(offset=50, limit=50)
            self.assertEqual(len(first), 50)
            self.assertFalse({r.id for r in first} & {r.id for r in second})
            self.assertEqual(service.list(keyword="存在しない"), [])

if __name__ == "__main__":
    unittest.main(verbosity=2)
