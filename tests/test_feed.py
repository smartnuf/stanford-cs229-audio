from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import feedlib  # noqa: E402
import validate_repo  # noqa: E402


class MetadataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.publication, cls.episodes = feedlib.load_catalog()

    def test_schema_sequence_and_uniqueness(self) -> None:
        feedlib.validate_catalog(self.publication, self.episodes)
        self.assertEqual(self.publication["schema_version"], 1)
        self.assertEqual([episode.number for episode in self.episodes], list(range(1, 21)))
        self.assertEqual(len({episode.title for episode in self.episodes}), 20)
        self.assertEqual(len({episode.filename for episode in self.episodes}), 20)
        self.assertEqual(len({episode.guid for episode in self.episodes}), 20)
        self.assertEqual(len({episode.enclosure_url for episode in self.episodes}), 20)

    def test_exact_enclosure_lengths_and_total(self) -> None:
        manifest = json.loads((ROOT / "data" / "media-manifest.json").read_text())
        expected = {f"CS229-lecture{row['lecture']:02d}.m4a": row["size_bytes"]
                    for row in manifest["records"]}
        self.assertEqual(
            {episode.filename: episode.size_bytes for episode in self.episodes}, expected)
        self.assertEqual(sum(expected.values()), 1_798_240_224)

    def test_guids_are_deterministic_and_golden_locked(self) -> None:
        self.assertEqual(feedlib.channel_guid(self.publication), validate_repo.EXPECTED_CHANNEL_GUID)
        self.assertEqual(self.publication["identity"]["episode_namespace"],
                         validate_repo.EXPECTED_EPISODE_NAMESPACE)
        self.assertEqual(self.episodes[0].guid, validate_repo.EXPECTED_FIRST_GUID)
        self.assertEqual(self.episodes[-1].guid, validate_repo.EXPECTED_LAST_GUID)
        namespace = uuid.UUID(validate_repo.EXPECTED_EPISODE_NAMESPACE)
        expected = [f"urn:uuid:{uuid.uuid5(namespace, f'lecture-{number:02d}')}"
                    for number in range(1, 21)]
        self.assertEqual([episode.guid for episode in self.episodes], expected)

    def test_all_transcript_and_source_links_are_exact(self) -> None:
        for episode in self.episodes:
            number = episode.number
            self.assertEqual(episode.source_video_url,
                             f"https://see.stanford.edu/videos/courses/see/CS229/CS229-lecture{number:02d}.mp4")
            self.assertEqual(episode.transcript_html_url,
                             "https://see.stanford.edu/materials/aimlcs229/transcripts/"
                             f"MachineLearning-Lecture{number:02d}.html")
            self.assertEqual(episode.transcript_pdf_url,
                             "https://see.stanford.edu/materials/aimlcs229/transcripts/"
                             f"MachineLearning-Lecture{number:02d}.pdf")

    def test_release_identity_and_asset_names(self) -> None:
        result = validate_repo.validate_manifests()
        self.assertEqual(result["release_media_assets"], 20)
        self.assertEqual([episode.filename for episode in self.episodes],
                         [f"CS229-lecture{number:02d}.m4a" for number in range(1, 21)])
        self.assertTrue(all("/releases/download/audio-v1.0.0/" in episode.enclosure_url
                            for episode in self.episodes))
        self.assertTrue(all(episode.enclosure_url.endswith("/" + episode.filename)
                            for episode in self.episodes))


class FeedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.publication, cls.episodes = feedlib.load_catalog()
        cls.raw = (ROOT / "docs" / "feed.xml").read_bytes()
        cls.channel = ET.fromstring(cls.raw).find("channel")
        assert cls.channel is not None

    def test_valid_rss_and_namespaces(self) -> None:
        self.assertEqual(validate_repo.validate_feed()["items"], 20)
        text = self.raw.decode()
        for prefix, namespace in feedlib.NAMESPACES.items():
            self.assertIn(f'xmlns:{prefix}="{namespace}"', text)

    def test_channel_identity_attribution_and_licence(self) -> None:
        self.assertEqual(self.channel.findtext("title"), validate_repo.EXPECTED_TITLE)
        self.assertEqual(self.channel.findtext(f"{{{feedlib.NS_ITUNES}}}type"), "serial")
        self.assertEqual(self.channel.findtext(f"{{{feedlib.NS_PODCAST}}}medium"), "course")
        self.assertEqual(self.channel.findtext(f"{{{feedlib.NS_PODCAST}}}guid"),
                         validate_repo.EXPECTED_CHANNEL_GUID)
        licence = self.channel.find(f"{{{feedlib.NS_PODCAST}}}license")
        self.assertIsNotNone(licence)
        assert licence is not None
        self.assertEqual(licence.text, "cc-by-nc-sa-4.0")
        self.assertEqual(licence.get("url"), "https://creativecommons.org/licenses/by-nc-sa/4.0/")
        description = self.channel.findtext("description", "")
        self.assertIn("Stanford Engineering Everywhere", description)
        self.assertIn("not endorsed", description)

    def test_episode_contract(self) -> None:
        items = self.channel.findall("item")
        self.assertEqual(len(items), 20)
        for episode, item in zip(self.episodes, items, strict=True):
            self.assertEqual(item.findtext(f"{{{feedlib.NS_ITUNES}}}episode"), str(episode.number))
            self.assertEqual(item.findtext(f"{{{feedlib.NS_ITUNES}}}episodeType"), "full")
            self.assertEqual(item.findtext(f"{{{feedlib.NS_ITUNES}}}duration"), episode.duration)
            guid = item.find("guid")
            self.assertIsNotNone(guid)
            assert guid is not None
            self.assertEqual((guid.text, guid.get("isPermaLink")), (episode.guid, "false"))
            enclosure = item.find("enclosure")
            self.assertIsNotNone(enclosure)
            assert enclosure is not None
            self.assertEqual(enclosure.attrib, {
                "url": episode.enclosure_url,
                "length": str(episode.size_bytes),
                "type": "audio/mp4",
            })
            transcripts = item.findall(f"{{{feedlib.NS_PODCAST}}}transcript")
            self.assertEqual(len(transcripts), 1)
            self.assertEqual(transcripts[0].attrib, {
                "url": episode.transcript_html_url,
                "type": "text/html",
                "language": "en-US",
            })
            description = item.findtext("description", "")
            self.assertIn(episode.transcript_pdf_url, description)
            self.assertIn("unofficial audio-only adaptation", description)
            self.assertIn("not endorsed", description)

    def test_no_invented_dates(self) -> None:
        self.assertNotIn(b"<pubDate>", self.raw)
        self.assertNotIn(b"<lastBuildDate>", self.raw)

    def test_xml_escapes_metadata(self) -> None:
        publication = json.loads(json.dumps(self.publication))
        publication["feed"]["description"] = "Research & development <independent>"
        raw = feedlib.build_feed(publication, self.episodes)
        parsed = ET.fromstring(raw).find("channel")
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.findtext("description"), "Research & development <independent>")
        self.assertIn(b"Research &amp; development &lt;independent&gt;", raw)

    def test_non_https_feed_url_is_rejected(self) -> None:
        publication = json.loads(json.dumps(self.publication))
        publication["feed"]["feed_url"] = "http://example.invalid/feed.xml"
        with self.assertRaisesRegex(ValueError, "HTTPS"):
            feedlib.validate_catalog(publication, self.episodes)

    def test_duplicate_episode_number_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "exactly 01 through 20"):
            feedlib.validate_catalog(self.publication, [self.episodes[0], *self.episodes[:-1]])

    def test_regeneration_is_byte_identical(self) -> None:
        self.assertEqual(feedlib.build_feed(self.publication, self.episodes), self.raw)
        self.assertEqual(feedlib.build_index(self.publication, self.episodes),
                         (ROOT / "docs" / "index.html").read_bytes())


class RepositorySafetyTests(unittest.TestCase):
    def make_repo(self, filename: str, content: bytes) -> Path:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        path = root / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        subprocess.run(["git", "add", "-f", filename], cwd=root, check=True)
        return root

    def test_current_repository_passes(self) -> None:
        result = validate_repo.validate_repository_safety()
        self.assertGreaterEqual(result["files_checked"], 20)

    def test_media_file_is_rejected(self) -> None:
        root = self.make_repo("lecture01.M4A", b"not media")
        with self.assertRaises(validate_repo.ValidationError):
            validate_repo.validate_repository_safety(root)

    def test_large_file_is_rejected(self) -> None:
        root = self.make_repo("large.bin", b"0" * validate_repo.MAX_TRACKED_BYTES)
        with self.assertRaises(validate_repo.ValidationError):
            validate_repo.validate_repository_safety(root)

    def test_credential_signature_is_rejected_without_echoing_it(self) -> None:
        fake = ("gh" + "p_" + "A" * 36).encode()
        root = self.make_repo("notes.txt", fake)
        with self.assertRaisesRegex(validate_repo.ValidationError, "notes.txt") as context:
            validate_repo.validate_repository_safety(root)
        self.assertNotIn(fake.decode(), str(context.exception))

    def test_ssh_private_keys_and_standard_filenames_are_rejected(self) -> None:
        fake_header = ("-----BEGIN " + "OPENSSH PRIVATE KEY-----").encode()
        root = self.make_repo("notes.txt", fake_header)
        with self.assertRaisesRegex(validate_repo.ValidationError, "notes.txt") as context:
            validate_repo.validate_repository_safety(root)
        self.assertNotIn(fake_header.decode(), str(context.exception))
        root = self.make_repo("id_ed25519", b"placeholder")
        with self.assertRaisesRegex(validate_repo.ValidationError, "id_ed25519"):
            validate_repo.validate_repository_safety(root)


class ArtworkTests(unittest.TestCase):
    def test_cover_is_square_rgb_jpeg(self) -> None:
        self.assertEqual(validate_repo.jpeg_dimensions(ROOT / "docs" / "cover.jpg"),
                         (3000, 3000, 3))
        self.assertEqual(validate_repo.validate_generated_site()["artwork"]["sha256"],
                         validate_repo.EXPECTED_COVER_SHA256)


class WorkflowTests(unittest.TestCase):
    def test_workflows_are_read_only_and_online_is_not_push_triggered(self) -> None:
        offline = (ROOT / ".github" / "workflows" / "validate.yml").read_text()
        online = (ROOT / ".github" / "workflows" / "online-integrity.yml").read_text()
        for workflow in (offline, online):
            self.assertIn("permissions:\n  contents: read", workflow)
            self.assertIn("actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683", workflow)
            self.assertIn("persist-credentials: false", workflow)
            self.assertIn("runs-on: ubuntu-24.04", workflow)
        self.assertIn("schedule:", online)
        self.assertIn("workflow_dispatch:", online)
        self.assertNotIn("\n  push:", online)
        self.assertNotIn("git push", online)
        self.assertIn("scripts/audit_history.py", offline)


if __name__ == "__main__":
    unittest.main()
