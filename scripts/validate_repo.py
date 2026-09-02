#!/usr/bin/env python3
"""Offline validation for metadata, generated feed, artwork, and repository safety."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlparse

from feedlib import (
    NAMESPACES, NS_ATOM, NS_ITUNES, NS_PODCAST, ROOT, build_feed,
    build_index, channel_guid, derived_channel_guid, episode_guid, load_catalog, outputs,
    validate_catalog,
)

MAX_TRACKED_BYTES = 5 * 1024 * 1024
EXPECTED_TITLE = "CS229 Machine Learning — Unofficial Audio Preservation Edition"
EXPECTED_CHANNEL_GUID = "469b7cc4-06ab-5668-9474-0d72dac20367"
EXPECTED_CHANNEL_GUID_NAMESPACE = "ead4c236-bf58-58c6-a2c6-a6b28d128cb6"
EXPECTED_CHANNEL_GUID_SEED = "smartnuf.github.io/stanford-cs229-audio/feed.xml"
EXPECTED_EPISODE_NAMESPACE = "89a4ee68-d293-55c5-aba9-ca5d1627d6a8"
EXPECTED_FIRST_GUID = "urn:uuid:b504132c-3181-5bc1-99dd-b114c9454842"
EXPECTED_LAST_GUID = "urn:uuid:a4cecbba-ea7a-5306-8f05-d9f014a381b0"
EXPECTED_COVER_SHA256 = "771c71f6720e573bf3aaa9190ff37794873a893d99de05683f2e4da370756c06"
EXPECTED_MASTER_ZIP_SIZE = 1_798_288_244
EXPECTED_MASTER_ZIP_SHA256 = "0c0e3bab4cf6f74a82f02a93f636c565fab02c3ab63332458ffeb58aee826953"
EXPECTED_ZENODO_DOI = "10.5281/zenodo.22261678"
EXPECTED_ZENODO_RECORD_ID = 22261678
FORBIDDEN_SUFFIXES = {
    ".m4a", ".mp4", ".m4v", ".mov", ".zip", ".tar", ".tgz", ".gz", ".xz",
    ".p12", ".pfx", ".pem", ".key",
}
FORBIDDEN_NAMES = {
    ".netrc", "netrc", "cookies.txt", "ia.ini", "credentials.json",
    "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519",
}
FORBIDDEN_TOP_LEVEL = {"staging", "build", "dist", "tmp", "temp"}
SECRET_PATTERNS = (
    re.compile(rb"gh[pousr]_[A-Za-z0-9]{30,}"),
    re.compile(rb"github_pat_[A-Za-z0-9_]{40,}"),
    re.compile(rb"AKIA[0-9A-Z]{16}"),
    re.compile(rb"sk-[A-Za-z0-9]{32,}"),
    re.compile(b"-----BEGIN " + rb"(?:OPENSSH |RSA |EC |DSA )?" + b"PRIVATE KEY-----"),
)


class ValidationError(RuntimeError):
    pass


def fail(condition: bool, message: str) -> None:
    if condition:
        raise ValidationError(message)


def repository_files(root: Path = ROOT) -> list[Path]:
    command = ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"]
    result = subprocess.run(command, cwd=root, check=True, capture_output=True)
    deleted_result = subprocess.run(
        ["git", "ls-files", "--deleted", "-z"], cwd=root, check=True, capture_output=True)
    deleted = {name for name in deleted_result.stdout.split(b"\0") if name}
    return [root / name.decode("utf-8") for name in result.stdout.split(b"\0")
            if name and name not in deleted]


def validate_repository_safety(root: Path = ROOT) -> dict:
    files = repository_files(root)
    fail(not files, "Repository has no auditable files")
    for path in files:
        relative = path.relative_to(root)
        lower = path.name.lower()
        fail(path.is_symlink(), f"Tracked symlink is not permitted: {relative}")
        fail(not path.is_file(), f"Tracked path is not a regular file: {relative}")
        fail(path.stat().st_size >= MAX_TRACKED_BYTES, f"File meets/exceeds 5 MiB limit: {relative}")
        fail(path.suffix.lower() in FORBIDDEN_SUFFIXES, f"Forbidden media/archive/key file: {relative}")
        fail(lower in FORBIDDEN_NAMES or lower == ".env" or lower.startswith(".env."),
             f"Forbidden credential/config filename: {relative}")
        fail(relative.parts[0].lower() in FORBIDDEN_TOP_LEVEL,
             f"Generated staging directory is not permitted: {relative}")
        content = path.read_bytes()
        for pattern in SECRET_PATTERNS:
            fail(bool(pattern.search(content)), f"Credential signature detected in: {relative}")
    return {"files_checked": len(files), "maximum_bytes_exclusive": MAX_TRACKED_BYTES}


def jpeg_dimensions(path: Path) -> tuple[int, int, int]:
    data = path.read_bytes()
    fail(not data.startswith(b"\xff\xd8"), "Artwork is not a JPEG")
    position = 2
    sof_markers = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
    while position + 9 < len(data):
        if data[position] != 0xFF:
            position += 1
            continue
        while position < len(data) and data[position] == 0xFF:
            position += 1
        marker = data[position]
        position += 1
        if marker in {0xD8, 0xD9} or 0xD0 <= marker <= 0xD7:
            continue
        fail(position + 2 > len(data), "Truncated JPEG marker")
        length = int.from_bytes(data[position:position + 2], "big")
        fail(length < 2 or position + length > len(data), "Invalid JPEG marker length")
        if marker in sof_markers:
            height = int.from_bytes(data[position + 3:position + 5], "big")
            width = int.from_bytes(data[position + 5:position + 7], "big")
            components = data[position + 7]
            return width, height, components
        position += length
    raise ValidationError("JPEG has no supported frame header")


def validate_manifests(root: Path = ROOT) -> dict:
    publication, episodes = load_catalog(root)
    validate_catalog(publication, episodes)
    fail(publication["feed"]["title"] != EXPECTED_TITLE, "Public feed title changed")
    fail(publication["identity"]["channel_guid"] != EXPECTED_CHANNEL_GUID,
         "Pinned channel GUID changed")
    fail(publication["identity"]["channel_guid_namespace"] != EXPECTED_CHANNEL_GUID_NAMESPACE
         or publication["identity"]["channel_guid_seed"] != EXPECTED_CHANNEL_GUID_SEED
         or derived_channel_guid(publication) != EXPECTED_CHANNEL_GUID,
         "Channel GUID derivation contract changed")
    fail(publication["identity"]["episode_namespace"] != EXPECTED_EPISODE_NAMESPACE,
         "Pinned episode namespace changed")
    fail(episode_guid(publication, 1) != EXPECTED_FIRST_GUID
         or episode_guid(publication, 20) != EXPECTED_LAST_GUID,
         "Golden episode GUIDs changed")
    media = json.loads((root / "data" / "media-manifest.json").read_text())
    fail(media.get("result") != "pass", "Supplied media manifest is not passing")
    fail(media.get("media_files") != 20, "Media manifest count changed")
    fail(media.get("total_size_bytes") != 1_798_240_224, "Media manifest total changed")

    checksum_rows = {}
    for line in (root / "provenance" / "SHA256SUMS").read_text().splitlines():
        digest, filename = line.split(maxsplit=1)
        checksum_rows[filename] = digest
    fail(len(checksum_rows) != 20, "SHA256SUMS must have exactly 20 rows")
    for episode in episodes:
        fail(checksum_rows.get(episode.source_filename) != episode.sha256,
             f"Checksum mismatch for {episode.source_filename}")
        fail(not re.fullmatch(r"[0-9a-f]{64}", episode.sha256),
             f"Invalid SHA-256 for {episode.filename}")
    release = publication["media"]
    publication_status = publication.get("publication_status")
    fail(publication_status not in {"prepared", "published"},
         "Publication status must be prepared or published")
    release_commit = release.get("release_commit")
    if publication_status == "prepared":
        fail(release_commit is not None, "Prepared publication must not claim a release commit")
    else:
        fail(not isinstance(release_commit, str)
             or not re.fullmatch(r"[0-9a-f]{40}", release_commit),
             "Published release commit is missing or malformed")
    fail(release.get("repository") != "smartnuf/stanford-cs229-audio",
         "Release repository changed")
    fail(release.get("release_tag") != "audio-v1.0.0", "Release tag changed")
    expected_base = ("https://github.com/smartnuf/stanford-cs229-audio/"
                     "releases/download/audio-v1.0.0/")
    fail(release.get("base_url") != expected_base, "Release asset base URL changed")
    fail(release.get("release_url") !=
         "https://github.com/smartnuf/stanford-cs229-audio/releases/tag/audio-v1.0.0",
         "Release page URL changed")
    release_assets = json.loads((root / "data" / "release-assets.json").read_text())
    assets = release_assets.get("assets", [])
    fail(release_assets.get("schema_version") != 1 or release_assets.get("asset_count") != 27,
         "Release asset manifest count/schema mismatch")
    fail(release_assets.get("repository") != release["repository"]
         or release_assets.get("tag") != release["release_tag"],
         "Release asset manifest identity mismatch")
    expected_media_names = [episode.filename for episode in episodes]
    fail([row.get("name") for row in assets[:20]] != expected_media_names,
         "Release enclosure names/order mismatch")
    for episode, row in zip(episodes, assets[:20], strict=True):
        fail(row.get("role") != "podcast_enclosure"
             or row.get("size_bytes") != episode.size_bytes
             or row.get("sha256") != episode.sha256,
             f"Release enclosure manifest mismatch: {episode.filename}")
    expected_support_names = [
        "stanford-cs229-machine-learning-audio-edition-v1.0.zip",
        "stanford-cs229-machine-learning-audio-edition-v1.0.zip.sha256",
        "MANIFEST.json", "SHA256SUMS", "README.md", "LICENSE.md", "PROVENANCE.md",
    ]
    fail([row.get("name") for row in assets[20:]] != expected_support_names,
         "Release support asset names/order mismatch")
    master = assets[20]
    fail(master.get("role") != "master_archive"
         or master.get("size_bytes") != EXPECTED_MASTER_ZIP_SIZE
         or master.get("sha256") != EXPECTED_MASTER_ZIP_SHA256,
         "Canonical master ZIP identity mismatch")
    for row in assets:
        fail(not isinstance(row.get("size_bytes"), int) or row["size_bytes"] <= 0,
             f"Invalid release asset size: {row.get('name')}")
        fail(not re.fullmatch(r"[0-9a-f]{64}", row.get("sha256", "")),
             f"Invalid release asset SHA-256: {row.get('name')}")
    zenodo = json.loads((root / "zenodo" / "metadata.json").read_text())["metadata"]
    fail(zenodo.get("upload_type") != "video" or zenodo.get("version") != "1.0",
         "Zenodo type/version mismatch")
    fail(zenodo.get("license") != "cc-by-nc-sa-4.0"
         or zenodo.get("access_right") != "open", "Zenodo access/licence mismatch")
    fail(zenodo.get("creators") != [{"name": "smartnuf"}],
         "Zenodo preservation-curator creator changed")
    fail(zenodo.get("contributors") != [
        {"name": "Ng, Andrew", "type": "Other"},
        {"name": "Stanford Engineering Everywhere", "type": "Other"},
    ], "Zenodo contributor roles changed")
    fail(zenodo.get("title") != "CS229 Machine Learning — Unofficial Audio Preservation Edition",
         "Zenodo display title changed")
    for required in ("smartnuf is identified only as preservation curator/depositor",
                     "Andrew Ng is the course lecturer",
                     "neither is represented as having authored or endorsed"):
        fail(required not in zenodo.get("description", ""),
             "Zenodo description lacks role/non-endorsement wording")
    preservation = publication["preservation"]
    zenodo_record = json.loads((root / "data" / "zenodo-record.json").read_text())
    fail(zenodo_record.get("result") != "pass" or zenodo_record.get("schema_version") != 1,
         "Zenodo public verification record is not passing")
    fail(zenodo_record.get("record_id") != EXPECTED_ZENODO_RECORD_ID
         or zenodo_record.get("doi") != EXPECTED_ZENODO_DOI
         or zenodo_record.get("record_url") != preservation["record_url"]
         or zenodo_record.get("doi_url") != preservation["doi_url"],
         "Zenodo public identity mismatch")
    fail(zenodo_record.get("creator") != {
        "name": "smartnuf", "orcid": None, "affiliation": None,
        "role": "preservation curator/depositor",
    }, "Zenodo public curator identity mismatch")
    zenodo_files = zenodo_record.get("files", [])
    fail(zenodo_record.get("file_count") != 8 or len(zenodo_files) != 8,
         "Zenodo public file count mismatch")
    expected_zenodo_names = expected_support_names + ["ZENODO-METADATA.json"]
    fail([row.get("name") for row in zenodo_files] != expected_zenodo_names,
         "Zenodo public file inventory/order mismatch")
    release_by_name = {row["name"]: row for row in assets}
    for row in zenodo_files:
        name = row["name"]
        fail(not re.fullmatch(r"[0-9a-f]{32}", row.get("md5", "")),
             f"Invalid Zenodo MD5: {name}")
        fail(row.get("url") !=
             f"https://zenodo.org/api/records/{EXPECTED_ZENODO_RECORD_ID}/files/{name}/content",
             f"Unexpected Zenodo public file URL: {name}")
        if name == "ZENODO-METADATA.json":
            fail(row.get("sha256") != hashlib.sha256(
                (root / "zenodo" / "metadata.json").read_bytes()).hexdigest()
                or row.get("size_bytes") != (root / "zenodo" / "metadata.json").stat().st_size,
                "Published Zenodo metadata sidecar mismatch")
        else:
            expected_row = release_by_name[name]
            fail(row.get("size_bytes") != expected_row["size_bytes"]
                 or row.get("sha256") != expected_row["sha256"],
                 f"Published Zenodo file differs from release contract: {name}")
    verification = zenodo_record.get("verification", {})
    for key, value in {
        "public_api_metadata": "pass",
        "doi_resolution": "pass",
        "head_lengths": "pass_8_of_8",
        "server_md5": "pass_8_of_8",
        "sidecar_sha256_downloads": "pass_7_of_7",
        "master_zip_first_byte_range": "pass_206",
        "master_zip_last_byte_range": "pass_206",
    }.items():
        fail(verification.get(key) != value, f"Zenodo verification evidence mismatch: {key}")
    return {
        "episodes": len(episodes),
        "total_enclosure_bytes": sum(episode.size_bytes for episode in episodes),
        "channel_guid": channel_guid(publication),
        "first_episode_guid": episode_guid(publication, 1),
        "last_episode_guid": episode_guid(publication, 20),
        "release_media_assets": len(episodes),
        "release_assets": len(assets),
        "publication_status": publication_status,
        "release_commit": release_commit,
        "master_zip_sha256": master["sha256"],
        "zenodo_record_id": zenodo_record["record_id"],
        "zenodo_doi": zenodo_record["doi"],
    }


def _ascii_https(url: str, label: str) -> None:
    try:
        url.encode("ascii")
    except UnicodeEncodeError as error:
        raise ValidationError(f"{label} URL is not ASCII") from error
    parsed = urlparse(url)
    fail(parsed.scheme != "https" or not parsed.netloc, f"{label} URL is not absolute HTTPS")


def validate_feed(root: Path = ROOT) -> dict:
    publication, episodes = load_catalog(root)
    path = root / "docs" / "feed.xml"
    raw = path.read_bytes()
    fail(raw != build_feed(publication, episodes), "docs/feed.xml is not deterministic/current")
    text = raw.decode("utf-8")
    for prefix, namespace in NAMESPACES.items():
        fail(f'xmlns:{prefix}="{namespace}"' not in text, f"Missing {prefix} namespace declaration")
    fail("<pubDate>" in text or "<lastBuildDate>" in text, "Feed must not invent dates")

    root_element = ET.fromstring(raw)
    fail(root_element.tag != "rss" or root_element.get("version") != "2.0", "Expected RSS 2.0")
    channel = root_element.find("channel")
    fail(channel is None, "Missing channel")
    assert channel is not None
    feed = publication["feed"]
    course = publication["course"]
    licence = publication["license"]
    fail(channel.findtext("title") != EXPECTED_TITLE, "Channel title mismatch")
    fail(channel.findtext("link") != course["source_url"], "Channel source link mismatch")
    fail(channel.findtext("language") != "en-us", "Channel language mismatch")
    fail(channel.findtext(f"{{{NS_ITUNES}}}type") != "serial", "Feed is not serial")
    fail(channel.findtext(f"{{{NS_ITUNES}}}explicit") != "false", "Feed explicit flag mismatch")
    fail(channel.findtext(f"{{{NS_ITUNES}}}author") != "Andrew Ng (lecturer)",
         "Channel author must identify Andrew Ng only as lecturer")
    channel_description = channel.findtext("description", "")
    for required in ("Andrew Ng", "Stanford Engineering Everywhere", "independent",
                     "not endorsed by Stanford University or Andrew Ng"):
        fail(required not in channel_description, "Channel description lacks required attribution/disclaimer")
    fail(channel.findtext(f"{{{NS_PODCAST}}}guid") != channel_guid(publication), "Channel GUID mismatch")
    fail(channel.findtext(f"{{{NS_PODCAST}}}medium") != "course", "Podcast medium mismatch")
    licence_node = channel.find(f"{{{NS_PODCAST}}}license")
    fail(licence_node is None or licence_node.text != licence["identifier"]
         or licence_node.get("url") != licence["url"], "Podcast licence mismatch")
    self_link = channel.find(f"{{{NS_ATOM}}}link")
    fail(self_link is None or self_link.get("rel") != "self"
         or self_link.get("type") != "application/rss+xml"
         or self_link.get("href") != feed["feed_url"], "Atom self link mismatch")
    related_links = [node for node in channel.findall(f"{{{NS_ATOM}}}link")
                     if node.get("rel") == "related"]
    fail(len(related_links) != 1
         or related_links[0].get("href") != publication["preservation"]["doi_url"]
         or related_links[0].get("type") != "text/html",
         "Atom Zenodo preservation link mismatch")
    image = channel.find(f"{{{NS_ITUNES}}}image")
    fail(image is None or image.get("href") != feed["artwork_url"], "Artwork URL mismatch")
    for label, url in (("feed", feed["feed_url"]), ("artwork", feed["artwork_url"]),
                       ("course", course["source_url"])):
        _ascii_https(url, label)

    items = channel.findall("item")
    fail(len(items) != 20, "Feed must contain exactly 20 items")
    enclosure_urls: set[str] = set()
    item_guids: set[str] = set()
    for episode, item in zip(episodes, items, strict=True):
        prefix = f"Lecture {episode.number:02d}"
        fail(item.findtext("title") != f"{prefix} — {episode.title}", f"Title mismatch: {prefix}")
        fail(item.findtext("link") != episode.source_video_url, f"Source link mismatch: {prefix}")
        guid = item.find("guid")
        fail(guid is None or guid.text != episode.guid or guid.get("isPermaLink") != "false",
             f"GUID mismatch: {prefix}")
        item_guids.add(guid.text or "")
        fail(item.findtext(f"{{{NS_ITUNES}}}episode") != str(episode.number),
             f"Episode number mismatch: {prefix}")
        fail(item.findtext(f"{{{NS_ITUNES}}}episodeType") != "full",
             f"Episode type mismatch: {prefix}")
        fail(item.findtext(f"{{{NS_ITUNES}}}duration") != episode.duration,
             f"Duration mismatch: {prefix}")
        enclosure = item.find("enclosure")
        fail(enclosure is None, f"Missing enclosure: {prefix}")
        assert enclosure is not None
        fail(enclosure.get("url") != episode.enclosure_url, f"Enclosure URL mismatch: {prefix}")
        fail(enclosure.get("length") != str(episode.size_bytes), f"Enclosure size mismatch: {prefix}")
        fail(enclosure.get("type") != "audio/mp4", f"Enclosure MIME mismatch: {prefix}")
        _ascii_https(enclosure.get("url", ""), f"{prefix} enclosure")
        enclosure_urls.add(enclosure.get("url", ""))
        description = item.findtext("description", "")
        for required in (episode.source_video_url, episode.transcript_html_url,
                         episode.transcript_pdf_url, "unofficial audio-only adaptation",
                         "not endorsed", licence["short_name"], licence["url"]):
            fail(required not in description, f"Description lacks required attribution/link: {prefix}")
        transcripts = item.findall(f"{{{NS_PODCAST}}}transcript")
        fail(len(transcripts) != 1, f"Expected one HTML transcript: {prefix}")
        transcript = transcripts[0]
        fail(transcript.get("url") != episode.transcript_html_url
             or transcript.get("type") != "text/html"
             or transcript.get("language") != "en-US"
             or transcript.get("rel") is not None, f"Transcript metadata mismatch: {prefix}")
    fail(len(enclosure_urls) != 20, "Enclosure URLs are not unique")
    fail(len(item_guids) != 20, "Item GUIDs are not unique")
    fail(bool(re.search(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", text, re.IGNORECASE)),
         "Feed contains an unapproved public email address")
    return {"items": len(items), "unique_guids": len(item_guids), "unique_enclosures": len(enclosure_urls)}


def validate_generated_site(root: Path = ROOT) -> dict:
    expected = outputs(root)
    stale = [str(path.relative_to(root)) for path, content in expected.items()
             if not path.is_file() or path.read_bytes() != content]
    fail(bool(stale), "Stale generated files: " + ", ".join(stale))
    width, height, components = jpeg_dimensions(root / "docs" / "cover.jpg")
    fail((width, height, components) != (3000, 3000, 3),
         "Artwork must be a 3000x3000 three-component JPEG")
    cover_hash = hashlib.sha256((root / "docs" / "cover.jpg").read_bytes()).hexdigest()
    fail(cover_hash != EXPECTED_COVER_SHA256, "Public artwork golden hash changed")
    index = (root / "docs" / "index.html").read_text(encoding="utf-8")
    publication, episodes = load_catalog(root)
    fail(index.count("<li>") != 20, "Landing page must list exactly 20 generated lectures")
    fail(publication["feed"]["feed_url"].rsplit("/", 1)[-1] not in index,
         "Landing page does not link the feed")
    fail(publication["preservation"]["doi_url"] not in index,
         "Landing page does not link the Zenodo preservation record")
    return {"generated_files": len(expected), "artwork": {
        "width": width, "height": height, "components": components, "sha256": cover_hash}}


def run_all(root: Path = ROOT) -> dict:
    return {
        "result": "pass",
        "manifests": validate_manifests(root),
        "feed": validate_feed(root),
        "site": validate_generated_site(root),
        "repository_safety": validate_repository_safety(root),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="optional JSON report path")
    args = parser.parse_args()
    try:
        report = run_all()
    except (ValidationError, ValueError, KeyError, ET.ParseError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    rendered = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
