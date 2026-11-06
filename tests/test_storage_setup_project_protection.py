from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from backend.app.core.storage_setup import apply_setup


class StorageSetupProjectProtectionTests(unittest.TestCase):
    def _write_config(
        self, config: Path, root: Path, project_id: str = "P001", project_name: str = "工事A"
    ) -> None:
        config.write_text(
            json.dumps(
                {
                    "project_id": project_id,
                    "project_name": project_name,
                    "data_root": str(root),
                    "storage_type": "local",
                    "setup_completed": True,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8-sig",
        )

    def _write_marker(self, root: Path, project_id: str = "P001", project_name: str = "工事A") -> Path:
        marker = root / ".ky_site.json"
        marker.write_text(
            json.dumps({"project_id": project_id, "project_name": project_name}, ensure_ascii=False),
            encoding="utf-8",
        )
        return marker

    def _write_record(self, root: Path, name: str, project_id: str) -> Path:
        record = root / "records" / "2026-11" / f"{name}.json"
        record.parent.mkdir(parents=True, exist_ok=True)
        record.write_text(json.dumps({"schema_version": 1, "project_id": project_id}), encoding="utf-8")
        return record

    def test_new_empty_folder_is_initialized_without_data_subfolder(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            root, config = base / "site", base / "config.json"
            root.mkdir()

            ok, _ = apply_setup(config, str(root), "P001", "工事A", "local")

            self.assertTrue(ok)
            self.assertEqual(
                {"export", "images", "records", "reports", "usage"},
                {path.name for path in root.iterdir() if path.is_dir()},
            )
            self.assertFalse((root / "data").exists())
            self.assertEqual("P001", json.loads((root / ".ky_site.json").read_text(encoding="utf-8"))["project_id"])

    def test_existing_valid_marker_is_recognized_and_not_rewritten(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            root, config = base / "site", base / "config.json"
            root.mkdir()
            marker = self._write_marker(root, "EXISTING", "既存工事")
            original = marker.read_bytes()

            ok, _ = apply_setup(config, str(root), "入力値", "入力工事", "local")

            self.assertTrue(ok)
            self.assertEqual(original, marker.read_bytes())
            saved = json.loads(config.read_text(encoding="utf-8-sig"))
            self.assertEqual(("EXISTING", "既存工事"), (saved["project_id"], saved["project_name"]))

    def test_changing_confirmed_project_id_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            root, config = base / "site", base / "config.json"
            root.mkdir()
            self._write_marker(root)
            self._write_config(config, root)
            original = config.read_bytes()

            ok, message = apply_setup(config, str(root), "P999", "工事A", "local")

            self.assertFalse(ok)
            self.assertIn("変更できません", message)
            self.assertEqual(original, config.read_bytes())

    def test_missing_marker_with_existing_history_is_protected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            root, config = base / "site", base / "config.json"
            root.mkdir()
            record = self._write_record(root, "one", "P001")
            original = record.read_bytes()

            ok, message = apply_setup(config, str(root), "NEW", "新規", "local")

            self.assertFalse(ok)
            self.assertIn("管理者", message)
            self.assertFalse((root / ".ky_site.json").exists())
            self.assertFalse(config.exists())
            self.assertEqual(original, record.read_bytes())

    def test_broken_marker_is_protected_and_not_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            root, config = base / "site", base / "config.json"
            root.mkdir()
            marker = root / ".ky_site.json"
            marker.write_text("{broken", encoding="utf-8")
            self._write_record(root, "one", "P001")
            original = marker.read_bytes()

            ok, message = apply_setup(config, str(root), "NEW", "新規", "local")

            self.assertFalse(ok)
            self.assertIn("破損", message)
            self.assertEqual(original, marker.read_bytes())
            self.assertFalse(config.exists())

    def test_multiple_record_project_ids_are_protected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            root, config = base / "site", base / "config.json"
            root.mkdir()
            self._write_marker(root)
            self._write_record(root, "one", "P001")
            self._write_record(root, "two", "P002")

            ok, message = apply_setup(config, str(root), "P001", "工事A", "local")

            self.assertFalse(ok)
            self.assertIn("複数", message)
            self.assertFalse(config.exists())

    def test_project_name_change_preserves_history_and_marker(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            root, config = base / "site", base / "config.json"
            root.mkdir()
            marker = self._write_marker(root)
            record = self._write_record(root, "one", "P001")
            self._write_config(config, root)
            marker_before, record_before = marker.read_bytes(), record.read_bytes()

            ok, _ = apply_setup(config, str(root), "P001", "表示名変更", "local")

            self.assertTrue(ok)
            self.assertEqual("表示名変更", json.loads(config.read_text(encoding="utf-8-sig"))["project_name"])
            self.assertEqual(marker_before, marker.read_bytes())
            self.assertEqual(record_before, record.read_bytes())

    def test_second_pc_inherits_marker_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            root, config = base / "site", base / "second-pc-config.json"
            root.mkdir()
            self._write_marker(root, "SHARED", "共有工事")
            self._write_record(root, "one", "SHARED")

            ok, _ = apply_setup(config, str(root), "手入力", "手入力名", "nas")

            self.assertTrue(ok)
            saved = json.loads(config.read_text(encoding="utf-8-sig"))
            self.assertEqual(("SHARED", "共有工事"), (saved["project_id"], saved["project_name"]))


if __name__ == "__main__":
    unittest.main()
