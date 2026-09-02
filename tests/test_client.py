from __future__ import annotations

import re
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import check_client  # noqa: E402
import feedlib  # noqa: E402


class ClientFeedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.publication, cls.canonical = feedlib.load_catalog()
        cls.raw = (ROOT / "docs" / "feed.xml").read_bytes()

    def test_live_feed_parser_contract(self) -> None:
        episodes = check_client.parse_feed(
            self.raw, self.publication["feed"]["feed_url"])
        self.assertEqual([episode.number for episode in episodes], list(range(1, 21)))
        self.assertEqual([episode.guid for episode in episodes],
                         [episode.guid for episode in self.canonical])
        self.assertTrue(all(episode.mime_type == "audio/mp4" for episode in episodes))

    def test_feed_parser_rejects_changed_order(self) -> None:
        root = ET.fromstring(self.raw)
        channel = root.find("channel")
        assert channel is not None
        items = channel.findall("item")
        first_index = list(channel).index(items[0])
        channel.remove(items[0])
        channel.insert(first_index + 1, items[0])
        with self.assertRaisesRegex(check_client.SemanticFailure, "order"):
            check_client.parse_feed(
                ET.tostring(root), self.publication["feed"]["feed_url"])

    def test_feed_parser_rejects_wrong_target_url(self) -> None:
        with self.assertRaisesRegex(check_client.SemanticFailure, "requested feed URL"):
            check_client.parse_feed(self.raw, "https://example.invalid/feed.xml")

    def test_scope_is_bounded(self) -> None:
        self.assertEqual(check_client.selected_numbers("smoke"), [1, 10, 20])
        self.assertEqual(check_client.selected_numbers("full"), list(range(1, 21)))
        with self.assertRaises(ValueError):
            check_client.selected_numbers("unknown")

    def test_execution_trace_identifies_revision(self) -> None:
        identity = check_client.execution_identity()
        self.assertRegex(identity["git_commit"], re.compile(r"^[0-9a-f]{40}$"))
        self.assertTrue(identity["python"])
        self.assertTrue(identity["operating_system"])

    def test_seek_offsets_cover_start_middle_and_end(self) -> None:
        points = check_client.seek_offsets(5400.0, 5.0)
        self.assertEqual(points, [0.0, 300.0, 5375.0])

    def test_ffmpeg_progress_parser(self) -> None:
        progress = "out_time_us=1000000\nprogress=continue\nout_time_us=5013333\nprogress=end\n"
        self.assertAlmostEqual(check_client.decoded_seconds(progress), 5.013333)

    def test_gpodder_listing_requires_every_guid_once(self) -> None:
        episodes = check_client.parse_feed(
            self.raw, self.publication["feed"]["feed_url"])
        listing = "\n".join(episode.guid for episode in episodes)
        check_client.validate_gpodder_listing(listing, episodes)
        with self.assertRaisesRegex(check_client.SemanticFailure, r"\[20\]"):
            check_client.validate_gpodder_listing(
                "\n".join(episode.guid for episode in episodes[:-1]), episodes)


if __name__ == "__main__":
    unittest.main()
