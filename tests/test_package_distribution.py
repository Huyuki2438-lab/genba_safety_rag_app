import json
import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.package_distribution import (
    SECRET_FIELDS,
    SITE_FOLDERS,
    create_site_structure,
    default_config,
    install_pricing_config,
    load_distribution_secrets,
    parse_args,
    assemble_distribution,
    write_secrets_env,
)


class PackageDistributionStructureTests(unittest.TestCase):
    DUMMY_VALUES = {
        "VERTEX_API_KEY": "test_key_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
        "GEMINI_MODEL": "gemini-test-model",
        "GOOGLE_CLOUD_PROJECT": "test-project-123456",
        "GOOGLE_CLOUD_LOCATION": "us-central1",
    }

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

    def test_distribution_option_is_required(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            parse_args([])

    def test_copy_env_settings_are_written_in_fixed_order(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "copy.env"
            source.write_text(
                "".join(f"{name}={self.DUMMY_VALUES[name]}\n" for name in SECRET_FIELDS),
                encoding="utf-8",
            )
            pc_dir = root / "new-pc-package"
            pc_dir.mkdir()

            loaded = load_distribution_secrets(source)
            target = write_secrets_env(pc_dir, loaded)

            self.assertEqual(
                target.read_text(encoding="utf-8"),
                "".join(f"{name}={self.DUMMY_VALUES[name]}\n" for name in SECRET_FIELDS),
            )

    def test_missing_key_stops_before_secrets_file_is_created(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "copy.env"
            source.write_text(
                "GEMINI_MODEL=gemini-test-model\n"
                "GOOGLE_CLOUD_PROJECT=test-project-123456\n"
                "GOOGLE_CLOUD_LOCATION=us-central1\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "VERTEX_API_KEY"):
                load_distribution_secrets(source)
            self.assertFalse((root / "new-pc-package" / "secrets.env").exists())

    def test_invalid_key_error_does_not_echo_key(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "copy.env"
            invalid_key = "invalid key value that must stay secret"
            values = dict(self.DUMMY_VALUES, VERTEX_API_KEY=invalid_key)
            source.write_text(
                "".join(f"{name}={values[name]}\n" for name in SECRET_FIELDS),
                encoding="utf-8",
            )

            with self.assertRaises(ValueError) as raised:
                load_distribution_secrets(source)
            self.assertNotIn(invalid_key, str(raised.exception))

    def test_existing_secrets_file_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pc_dir = Path(temp_dir)
            target = pc_dir / "secrets.env"
            target.write_text("existing", encoding="utf-8")

            with self.assertRaises(FileExistsError):
                write_secrets_env(pc_dir, self.DUMMY_VALUES)
            self.assertEqual(target.read_text(encoding="utf-8"), "existing")

    def test_existing_distribution_candidate_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "existing-candidate"
            output.mkdir()
            marker = output / "keep.txt"
            marker.write_text("keep", encoding="utf-8")

            with self.assertRaises(FileExistsError):
                assemble_distribution(output, Path(temp_dir) / "missing-copy.env")
            self.assertEqual(marker.read_text(encoding="utf-8"), "keep")

    def test_missing_copy_source_does_not_fall_back_to_old_secrets(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            old_secrets = root / "secrets.env"
            old_secrets.write_text(
                "".join(f"{name}={self.DUMMY_VALUES[name]}\n" for name in SECRET_FIELDS),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "source file was not found"):
                load_distribution_secrets(root / "missing-copy.env")

    def test_failed_assembly_leaves_no_candidate_or_staging_folder(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output = root / "new-candidate"
            source = root / "copy.env"
            source.write_text(
                "".join(f"{name}={self.DUMMY_VALUES[name]}\n" for name in SECRET_FIELDS),
                encoding="utf-8",
            )

            def fail_after_start(stage, _env):
                stage.mkdir(parents=True)
                (stage / "partial.txt").write_text("partial", encoding="utf-8")
                raise OSError("simulated assembly failure")

            with patch("scripts.package_distribution._assemble_into", side_effect=fail_after_start):
                with self.assertRaises(OSError):
                    assemble_distribution(output, source)

            self.assertFalse(output.exists())
            self.assertEqual(list(root.glob(".new-candidate.assembling-*")), [])


if __name__ == "__main__":
    unittest.main()
