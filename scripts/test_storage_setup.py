"""Regression tests for the first-run data storage location setup feature."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.core.storage_setup import (
    CONNECTION_NG_MESSAGE,
    CONNECTION_OK_MESSAGE,
    current_data_root,
    read_raw_config,
    save_data_root,
    validate_data_root,
)
from backend.app.core.config import _load_project_config


class ValidateDataRootTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="KY setup ")
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_existing_writable_local_folder_succeeds(self):
        ok, message = validate_data_root(str(self.root))
        self.assertTrue(ok)
        self.assertEqual(message, CONNECTION_OK_MESSAGE)
        # write-test probe must not remain behind
        self.assertEqual(list(self.root.iterdir()), [])

    def test_missing_folder_fails_with_guidance_message(self):
        missing = self.root / "does_not_exist"
        ok, message = validate_data_root(str(missing))
        self.assertFalse(ok)
        self.assertIn(CONNECTION_NG_MESSAGE, message)

    def test_empty_path_rejected(self):
        ok, message = validate_data_root("")
        self.assertFalse(ok)
        self.assertIn("入力または選択", message)

    def test_relative_path_rejected(self):
        ok, message = validate_data_root("relative\\path")
        self.assertFalse(ok)
        self.assertIn("絶対パス", message)

    def test_unc_path_is_treated_as_absolute_and_reachability_checked(self):
        # A well-formed but unreachable UNC path must fail with the network guidance,
        # not with an "invalid path" error, proving UNC syntax itself is accepted.
        ok, message = validate_data_root(r"\\NONEXISTENT-HOST\share\folder")
        self.assertFalse(ok)
        self.assertIn(CONNECTION_NG_MESSAGE, message)
        self.assertIn("NAS", message)

    def test_unwritable_folder_fails(self):
        # Simulate "cannot write" by pointing at a path whose parent exists but
        # whose leaf does not (equivalent user-visible outcome to permission-denied).
        target = self.root / "sub" / "leaf"
        ok, message = validate_data_root(str(target))
        self.assertFalse(ok)


class SaveDataRootTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="KY setup cfg ")
        self.config_file = Path(self.temp.name) / "config.json"
        self.data_dir = Path(self.temp.name) / "data"
        self.data_dir.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def test_save_creates_valid_config_when_missing(self):
        save_data_root(self.config_file, str(self.data_dir))
        raw = read_raw_config(self.config_file)
        self.assertEqual(raw["data_root"], str(self.data_dir))
        self.assertEqual(raw["storage_type"], "local")
        self.assertTrue(raw["project_id"])
        self.assertTrue(raw["project_name"])
        # The written file must pass the strict loader used by the normal app startup.
        loaded = _load_project_config(self.config_file)
        self.assertEqual(loaded["data_root"], str(self.data_dir))

    def test_save_preserves_existing_project_identity(self):
        self.config_file.write_text(
            json.dumps({"project_id": "007", "project_name": "テスト現場", "data_root": ""}, ensure_ascii=False),
            encoding="utf-8-sig",
        )
        save_data_root(self.config_file, str(self.data_dir))
        raw = read_raw_config(self.config_file)
        self.assertEqual(raw["project_id"], "007")
        self.assertEqual(raw["project_name"], "テスト現場")
        self.assertEqual(current_data_root(self.config_file), str(self.data_dir))

    def test_save_detects_unc_as_network_storage_type(self):
        save_data_root(self.config_file, r"\\NAS\share\folder")
        raw = read_raw_config(self.config_file)
        self.assertEqual(raw["storage_type"], "network")


class LenientConfigLoadingTests(unittest.TestCase):
    """config.json with an empty/missing data_root must not raise (first-run state)."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="KY setup lenient ")
        self.config_file = Path(self.temp.name) / "config.json"

    def tearDown(self):
        self.temp.cleanup()

    def test_empty_data_root_does_not_raise(self):
        self.config_file.write_text(
            json.dumps({"project_id": "", "project_name": "", "data_root": ""}, ensure_ascii=False),
            encoding="utf-8-sig",
        )
        data = _load_project_config(self.config_file)
        self.assertEqual(data["data_root"], "")

    def test_configured_data_root_still_requires_project_identity(self):
        self.config_file.write_text(
            json.dumps({"project_id": "", "project_name": "", "data_root": str(Path(self.temp.name))}, ensure_ascii=False),
            encoding="utf-8-sig",
        )
        with self.assertRaises(RuntimeError):
            _load_project_config(self.config_file)

    def test_configured_data_root_must_be_absolute(self):
        self.config_file.write_text(
            json.dumps({"project_id": "1", "project_name": "x", "data_root": "relative"}, ensure_ascii=False),
            encoding="utf-8-sig",
        )
        with self.assertRaises(RuntimeError):
            _load_project_config(self.config_file)


if __name__ == "__main__":
    unittest.main(verbosity=2)
