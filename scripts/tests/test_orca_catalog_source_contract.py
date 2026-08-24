from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from scripts.check_orca_catalog_source import (
    DEFAULT_SOURCE_LOCK,
    SOURCE_LOCK_FORMAT,
    _read_source_lock,
)
from scripts.refresh_orca_catalog_source import _write_source_lock


class OrcaCatalogSourceContractTest(unittest.TestCase):
    def test_repository_tracks_metadata_instead_of_the_large_bundle(self) -> None:
        source_lock = _read_source_lock(DEFAULT_SOURCE_LOCK)
        workflow = (
            DEFAULT_SOURCE_LOCK.parents[4]
            / ".github"
            / "workflows"
            / "check-orca-catalog-source.yml"
        ).read_text(encoding="utf-8")

        self.assertEqual(source_lock["format"], SOURCE_LOCK_FORMAT)
        self.assertEqual(source_lock["source"], "orca")
        self.assertRegex(str(source_lock["commit"]), r"^[0-9a-f]{40}$")
        self.assertRegex(str(source_lock["profiles_tree"]), r"^[0-9a-f]{40}$")
        self.assertNotIn("bundle.zip", workflow)
        self.assertIn("check_orca_catalog_source.py --json", workflow)

    def test_refresh_writes_a_small_lock_from_the_bundle_manifest(self) -> None:
        manifest = {
            "source": "orca",
            "repository": "https://github.com/OrcaSlicer/OrcaSlicer",
            "ref": "main",
            "commit": "a" * 40,
            "commit_date": "2026-08-24T00:00:00Z",
            "profiles_tree": "b" * 40,
            "content_sha256": "c" * 64,
            "file_count": 12,
            "vendor_count": 3,
            "version": 2,
            "preset_field_inventory": {"filament": {"ignored": ["string"]}},
        }
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            bundle = root / "bundle.zip"
            source_lock = root / "source-lock.json"
            with zipfile.ZipFile(bundle, "w") as archive:
                archive.writestr("filamenthub-source.json", json.dumps(manifest))

            _write_source_lock(bundle, source_lock)
            tracked = json.loads(source_lock.read_text(encoding="utf-8"))

        self.assertEqual(tracked["format"], SOURCE_LOCK_FORMAT)
        self.assertEqual(tracked["commit"], "a" * 40)
        self.assertEqual(tracked["profiles_tree"], "b" * 40)
        self.assertNotIn("preset_field_inventory", tracked)
        self.assertRegex(tracked["bundle_sha256"], r"^[0-9a-f]{64}$")


if __name__ == "__main__":
    unittest.main()
