import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from create_update_package import create_package
from updater import safe_relative_path


class UpdatePackageTests(unittest.TestCase):
    def test_package_excludes_config_and_contains_hashes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            output = root / "output"
            source.mkdir()
            (source / "AccessView.exe").write_bytes(b"application")
            (source / "AccessViewUpdater.exe").write_bytes(b"updater")
            (source / "config.json").write_text(
                '{"server_ip":"private"}',
                encoding="utf-8",
            )

            package = create_package(
                source,
                output,
                "1.2.3",
                "1.0.0",
            )

            with zipfile.ZipFile(package) as archive:
                names = set(archive.namelist())
                manifest = json.loads(archive.read("update.json"))

            self.assertIn("payload/AccessView.exe", names)
            self.assertIn("payload/AccessViewUpdater.exe", names)
            self.assertNotIn("payload/config.json", names)
            self.assertIn("AccessView.exe", manifest["files"])

    def test_unsafe_paths_are_rejected(self):
        for value in (
            "../file.exe",
            "/absolute.exe",
            "C:/absolute.exe",
            "folder/../../file.exe",
            "config.json",
        ):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    safe_relative_path(value)


if __name__ == "__main__":
    unittest.main()
