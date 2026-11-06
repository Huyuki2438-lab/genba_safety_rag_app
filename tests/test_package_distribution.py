import json
import tempfile
import unittest
from pathlib import Path

from scripts.package_distribution import (
    SITE_FOLDERS, create_site_structure, default_config, install_pricing_config,
)


class PackageDistributionStructureTests(unittest.TestCase):
    def test_default_config_points_to_project_folder_itself(self):
        data_root = default_config()["data_root"]

        self.assertTrue(data_root.endswith(r"\001_芝原改良工事"))
        self.assertFalse(data_root.endswith(r"\data"))

    def test_site_structure_is_created_directly_under_project_folder(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project = Path(temp_dir) / "001_テスト工事"

            create_site_structure(project, "001", "テスト工事")

            self.assertEqual(
                {path.name for path in project.iterdir() if path.is_dir()},
                set(SITE_FOLDERS),
            )
            self.assertFalse((project / "data").exists())
            marker = json.loads((project / ".ky_site.json").read_text(encoding="utf-8"))
            self.assertEqual(marker, {"project_id": "001", "project_name": "テスト工事"})

    def test_template_has_no_fixed_site_marker(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            template = Path(temp_dir) / "template_project"

            create_site_structure(template)

            self.assertEqual(
                {path.name for path in template.iterdir() if path.is_dir()},
                set(SITE_FOLDERS),
            )
            self.assertFalse((template / "data").exists())
            self.assertFalse((template / ".ky_site.json").exists())

    def test_existing_site_marker_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project = Path(temp_dir) / "existing"
            project.mkdir()
            marker_path = project / ".ky_site.json"
            existing = {"project_id": "999", "project_name": "既存工事"}
            marker_path.write_text(json.dumps(existing, ensure_ascii=False), encoding="utf-8")

            create_site_structure(project, "001", "テスト工事")

            self.assertEqual(json.loads(marker_path.read_text(encoding="utf-8")), existing)

    def test_pricing_config_is_installed_beside_exe(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source.json"
            source.write_text('{"schema_version": 1}', encoding="utf-8")

            target = install_pricing_config(root / "pc", source)

            self.assertEqual(target, root / "pc" / "settings" / "usage_pricing.json")
            self.assertEqual(target.read_bytes(), source.read_bytes())

    def test_existing_pricing_config_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source.json"
            source.write_text('{"source": true}', encoding="utf-8")
            target = root / "pc" / "settings" / "usage_pricing.json"
            target.parent.mkdir(parents=True)
            target.write_text('{"existing": true}', encoding="utf-8")

            install_pricing_config(root / "pc", source)

            self.assertEqual(target.read_text(encoding="utf-8"), '{"existing": true}')


if __name__ == "__main__":
    unittest.main()
