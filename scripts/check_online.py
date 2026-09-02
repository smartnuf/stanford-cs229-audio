#!/usr/bin/env python3
"""Bounded, read-only checks for the live feed, artwork, media, and source links."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import socket
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from feedlib import ROOT, load_catalog

USER_AGENT = "cs229-audio-feed-integrity-check/1.0 (+https://github.com/smartnuf/cs229-unofficial-audio-feed)"
RETRIES = 3
TIMEOUT_SECONDS = 15
MAX_WORKERS = 8
TRANSIENT_HTTP = {408, 425, 429, 500, 502, 503, 504}
MEDIA_TYPES = {"audio/mp4", "audio/x-m4a"}


class NetworkUnavailable(RuntimeError):
    pass


class SemanticFailure(RuntimeError):
    pass


class HTTPFailure(SemanticFailure):
    def __init__(self, url: str, code: int):
        self.url = url
        self.code = code
        super().__init__(f"{url}: HTTP {code}")


def request(url: str, method: str = "HEAD", byte_range: bool = False, read_all: bool = False) -> dict:
    headers = {"User-Agent": USER_AGENT, "Accept-Encoding": "identity"}
    if byte_range:
        headers["Range"] = "bytes=0-0"
    last_error: Exception | None = None
    for attempt in range(RETRIES):
        try:
            req = urllib.request.Request(url, method=method, headers=headers)
            with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as response:
                body = response.read() if read_all else response.read(2 if byte_range else 1)
                if not response.url.startswith("https://"):
                    raise SemanticFailure(f"{url}: redirected to non-HTTPS URL")
                return {
                    "requested_url": url,
                    "final_url": response.url,
                    "status": response.status,
                    "content_type": response.headers.get_content_type(),
                    "content_length": int(response.headers["Content-Length"])
                    if response.headers.get("Content-Length") else None,
                    "content_range": response.headers.get("Content-Range"),
                    "last_modified": response.headers.get("Last-Modified"),
                    "body": body,
                }
        except urllib.error.HTTPError as error:
            if error.code not in TRANSIENT_HTTP:
                raise HTTPFailure(url, error.code) from error
            last_error = error
        except (urllib.error.URLError, TimeoutError, socket.timeout, OSError) as error:
            last_error = error
        if attempt + 1 < RETRIES:
            time.sleep(2 ** attempt)
    raise NetworkUnavailable(f"{url}: unavailable after {RETRIES} attempts ({type(last_error).__name__})")


def require_status(result: dict, expected: set[int], label: str) -> None:
    if result["status"] not in expected:
        raise SemanticFailure(f"{label}: HTTP {result['status']}, expected {sorted(expected)}")


def check_document(url: str, local_path: Path, expected_types: set[str], label: str) -> dict:
    head = request(url)
    require_status(head, {200}, f"{label} HEAD")
    result = request(url, method="GET", read_all=True)
    require_status(result, {200}, label)
    if result["content_type"] not in expected_types:
        raise SemanticFailure(f"{label}: unexpected content type {result['content_type']}")
    local = local_path.read_bytes()
    if head["content_length"] != len(local):
        raise SemanticFailure(f"{label}: HEAD length {head['content_length']} != {len(local)}")
    if head["content_type"] not in expected_types:
        raise SemanticFailure(f"{label}: unexpected HEAD content type {head['content_type']}")
    if result["body"] != local:
        raise SemanticFailure(f"{label}: live bytes differ from exact local artifact")
    return {k: v for k, v in result.items() if k != "body"} | {
        "size_bytes": len(local), "sha256": hashlib.sha256(local).hexdigest(),
        "head_status": head["status"], "last_modified": head.get("last_modified"),
    }


def check_link(url: str, label: str) -> dict:
    try:
        result = request(url)
    except HTTPFailure as error:
        if error.code not in {403, 405, 501}:
            raise
        result = request(url, method="GET", byte_range=True)
    require_status(result, {200, 204, 206}, label)
    return {k: v for k, v in result.items() if k != "body"}


def check_enclosure(url: str, expected_size: int, label: str) -> dict:
    head = request(url)
    require_status(head, {200}, f"{label} HEAD")
    if head["content_length"] != expected_size:
        raise SemanticFailure(
            f"{label}: HEAD length {head['content_length']} != {expected_size}")
    if head["content_type"] not in MEDIA_TYPES:
        raise SemanticFailure(f"{label}: incompatible content type {head['content_type']}")
    ranged = request(url, method="GET", byte_range=True)
    require_status(ranged, {206}, f"{label} range")
    if len(ranged["body"]) != 1:
        raise SemanticFailure(f"{label}: range body is not exactly one byte")
    expected_range = f"bytes 0-0/{expected_size}"
    if ranged["content_range"] != expected_range:
        raise SemanticFailure(f"{label}: Content-Range {ranged['content_range']} != {expected_range}")
    if ranged["content_length"] != 1:
        raise SemanticFailure(f"{label}: ranged Content-Length is not 1")
    return {
        "url": url, "size_bytes": expected_size, "content_type": head["content_type"],
        "head_status": head["status"], "range_status": ranged["status"],
        "content_range": ranged["content_range"],
    }


def check_archive_metadata(publication: dict, episodes: list) -> dict:
    identifier = publication["media"]["internet_archive_identifier"]
    url = f"https://archive.org/metadata/{identifier}"
    result = request(url, method="GET", read_all=True)
    require_status(result, {200}, "Internet Archive metadata")
    try:
        document = json.loads(result["body"])
    except json.JSONDecodeError as error:
        raise SemanticFailure("Internet Archive metadata is not valid JSON") from error
    metadata = document.get("metadata", {})
    if metadata.get("identifier") != identifier:
        raise SemanticFailure("Internet Archive identifier mismatch")
    if metadata.get("title") != publication["feed"]["title"]:
        raise SemanticFailure("Internet Archive title mismatch")
    if metadata.get("licenseurl") != publication["license"]["url"]:
        raise SemanticFailure("Internet Archive licence URL mismatch")

    expected_hashes = json.loads((ROOT / "data" / "archive-hashes.json").read_text())["records"]
    hashes_by_name = {row["filename"]: row for row in expected_hashes}
    files_by_name = {row.get("name"): row for row in document.get("files", []) if row.get("name")}
    expected_names = [episode.filename for episode in episodes]
    actual_m4a_names = sorted(name for name in files_by_name if name.lower().endswith(".m4a"))
    if actual_m4a_names != expected_names:
        raise SemanticFailure("Internet Archive M4A inventory differs from canonical 20 files")
    records = []
    for episode in episodes:
        remote = files_by_name[episode.filename]
        expected = hashes_by_name[episode.filename]
        if remote.get("source") != "original":
            raise SemanticFailure(f"{episode.filename}: Internet Archive file is not marked original")
        if int(remote.get("size", -1)) != episode.size_bytes:
            raise SemanticFailure(f"{episode.filename}: Internet Archive size mismatch")
        if remote.get("md5") != expected["md5"] or remote.get("sha1") != expected["sha1"]:
            raise SemanticFailure(f"{episode.filename}: Internet Archive exposed hash mismatch")
        records.append({
            "filename": episode.filename, "source": remote["source"],
            "size_bytes": int(remote["size"]), "md5": remote["md5"], "sha1": remote["sha1"],
        })
    public_files = json.loads((ROOT / "data" / "archive-item.json").read_text())["public_files"]
    missing_public_files = sorted(set(public_files) - set(files_by_name))
    if missing_public_files:
        raise SemanticFailure("Internet Archive item lacks approved public files: "
                              + ", ".join(missing_public_files))
    return {"url": url, "identifier": identifier, "canonical_originals": records,
            "approved_files_present": len(public_files)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="write detailed JSON report")
    args = parser.parse_args()
    publication, episodes = load_catalog()
    report: dict = {
        "schema_version": 1,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "result": "pass",
        "network_failures": [],
        "semantic_failures": [],
        "documents": {},
        "archive_item": None,
        "enclosures": [],
        "source_links": [],
    }

    checks = [
        ("landing_page", lambda: check_document(
            publication["feed"]["site_url"], ROOT / "docs" / "index.html", {"text/html"}, "landing page")),
        ("feed", lambda: check_document(
            publication["feed"]["feed_url"], ROOT / "docs" / "feed.xml",
            {"application/rss+xml", "application/xml", "text/xml"}, "feed")),
        ("artwork", lambda: check_document(
            publication["feed"]["artwork_url"], ROOT / "docs" / "cover.jpg",
            {"image/jpeg"}, "artwork")),
    ]
    for name, operation in checks:
        try:
            report["documents"][name] = operation()
        except NetworkUnavailable as error:
            report["network_failures"].append(str(error))
        except SemanticFailure as error:
            report["semantic_failures"].append(str(error))

    try:
        report["archive_item"] = check_archive_metadata(publication, episodes)
    except NetworkUnavailable as error:
        report["network_failures"].append(str(error))
    except SemanticFailure as error:
        report["semantic_failures"].append(str(error))

    operations = []
    for episode in episodes:
        label = f"lecture {episode.number:02d} enclosure"
        operations.append(("enclosure", episode.number, None, lambda episode=episode, label=label:
                           check_enclosure(episode.enclosure_url, episode.size_bytes, label)))
        for kind, url in (
            ("source_video", episode.source_video_url),
            ("transcript_html", episode.transcript_html_url),
            ("transcript_pdf", episode.transcript_pdf_url),
        ):
            operations.append(("source", episode.number, kind, lambda number=episode.number, kind=kind, url=url:
                               check_link(url, f"lecture {number:02d} {kind}")))

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(operation): (category, number, kind)
                   for category, number, kind, operation in operations}
        for future in concurrent.futures.as_completed(futures):
            category, number, kind = futures[future]
            try:
                result = future.result()
                if category == "enclosure":
                    report["enclosures"].append({"lecture": number, **result})
                else:
                    report["source_links"].append({"lecture": number, "kind": kind, **result})
            except NetworkUnavailable as error:
                report["network_failures"].append(str(error))
            except SemanticFailure as error:
                report["semantic_failures"].append(str(error))
    report["enclosures"].sort(key=lambda row: row["lecture"])
    report["source_links"].sort(key=lambda row: (row["lecture"], row["kind"]))

    if report["semantic_failures"]:
        report["result"] = "semantic_failure"
        exit_code = 1
    elif report["network_failures"]:
        report["result"] = "network_unavailable"
        exit_code = 2
    else:
        exit_code = 0
    rendered = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    print(json.dumps({
        "result": report["result"],
        "documents": len(report["documents"]),
        "archive_item": report["archive_item"] is not None,
        "enclosures": len(report["enclosures"]),
        "source_links": len(report["source_links"]),
        "network_failures": len(report["network_failures"]),
        "semantic_failures": len(report["semantic_failures"]),
    }, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
