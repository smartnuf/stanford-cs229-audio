from __future__ import annotations

import json
import stat
import sys
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_preservation  # noqa: E402
import validate_preservation  # noqa: E402


class PreservationContractTests(unittest.TestCase):
    def test_archive_name_and_inventory_are_stable(self) -> None:
        self.assertEqual(
            build_preservation.ZIP_NAME,
            "stanford-cs229-machine-learning-audio-edition-v1.0.zip",
        )
        names = validate_preservation.expected_names()
        self.assertEqual(len(names), 27)
        self.assertEqual(names[0], f"{build_preservation.PACKAGE_NAME}/")
        self.assertEqual(names[2], f"{build_preservation.PACKAGE_NAME}/audio/CS229-lecture01.m4a")
        self.assertEqual(names[21], f"{build_preservation.PACKAGE_NAME}/audio/CS229-lecture20.m4a")
        self.assertEqual(names[-1], f"{build_preservation.PACKAGE_NAME}/MANIFEST.json")

    def test_zip_metadata_is_fixed_and_stored(self) -> None:
        file_info = build_preservation.zip_info("root/file")
        directory_info = build_preservation.zip_info("root/", directory=True)
        self.assertEqual(file_info.date_time, build_preservation.FIXED_ZIP_TIME)
        self.assertEqual(file_info.compress_type, zipfile.ZIP_STORED)
        self.assertTrue(stat.S_ISREG(file_info.external_attr >> 16))
        self.assertEqual(stat.S_IMODE(file_info.external_attr >> 16), 0o644)
        self.assertTrue(stat.S_ISDIR(directory_info.external_attr >> 16))
        self.assertEqual(stat.S_IMODE(directory_info.external_attr >> 16), 0o755)

    def test_archive_paths_reject_traversal_and_absolute_names(self) -> None:
        self.assertTrue(validate_preservation.safe_name("root/audio/file.m4a"))
        self.assertFalse(validate_preservation.safe_name("../file"))
        self.assertFalse(validate_preservation.safe_name("/root/file"))

    def test_release_and_zenodo_manifests_are_complete(self) -> None:
        release = json.loads((ROOT / "data" / "release-assets.json").read_text())
        self.assertEqual(release["asset_count"], 27)
        self.assertEqual(sum(row["role"] == "podcast_enclosure" for row in release["assets"]), 20)
        self.assertEqual(sum(row["role"] == "master_archive" for row in release["assets"]), 1)
        zenodo = json.loads((ROOT / "zenodo" / "metadata.json").read_text())["metadata"]
        self.assertEqual(zenodo["license"], "cc-by-nc-sa-4.0")
        self.assertEqual(zenodo["creators"], [{"name": "smartnuf"}])
        self.assertNotIn("orcid", zenodo["creators"][0])
        self.assertNotIn("affiliation", zenodo["creators"][0])
        self.assertIn("preservation curator/depositor", zenodo["description"])
        record = json.loads((ROOT / "data" / "zenodo-record.json").read_text())
        self.assertEqual(record["doi"], "10.5281/zenodo.22261678")
        self.assertEqual(record["record_id"], 22261678)
        self.assertEqual(record["file_count"], 8)
        self.assertEqual(record["files"][0]["sha256"],
                         "0c0e3bab4cf6f74a82f02a93f636c565fab02c3ab63332458ffeb58aee826953")


if __name__ == "__main__":
    unittest.main()
