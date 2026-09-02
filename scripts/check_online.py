#!/usr/bin/env python3
"""Bounded read-only checks for Pages, release assets, and Stanford links."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import socket
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from feedlib import ROOT, load_catalog

USER_AGENT = "stanford-cs229-audio-integrity/1.0"
RETRIES = 3
TIMEOUT = 30
TRANSIENT = {408, 425, 429, 500, 502, 503, 504}
MEDIA_TYPES = {"audio/mp4", "audio/x-m4a", "application/octet-stream"}


class NetworkUnavailable(RuntimeError):
    pass


class SemanticFailure(RuntimeError):
    pass


class HTTPFailure(SemanticFailure):
    def __init__(self, url: str, code: int):
        self.code = code
        super().__init__(f"{url}: HTTP {code}")


def request(url: str, method: str = "HEAD", byte_range: str | None = None,
            read_all: bool = False) -> dict:
    headers = {"User-Agent": USER_AGENT, "Accept-Encoding": "identity"}
    if byte_range:
        headers["Range"] = byte_range
    last_error: Exception | None = None
    for attempt in range(RETRIES):
        try:
            req = urllib.request.Request(url, method=method, headers=headers)
            with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
                body = response.read() if read_all else response.read(2 if byte_range else 1)
                if not url.startswith("https://") or not response.url.startswith("https://"):
                    raise SemanticFailure(f"{url}: non-HTTPS request or redirect")
                return {
                    "url": url,
                    "final_url": response.url,
                    "status": response.status,
                    "content_type": response.headers.get_content_type(),
                    "content_length": int(response.headers["Content-Length"])
                    if response.headers.get("Content-Length") else None,
                    "content_range": response.headers.get("Content-Range"),
                    "body": body,
                }
        except urllib.error.HTTPError as error:
            if error.code not in TRANSIENT:
                raise HTTPFailure(url, error.code) from error
            last_error = error
        except (urllib.error.URLError, TimeoutError, socket.timeout, OSError) as error:
            last_error = error
        if attempt + 1 < RETRIES:
            time.sleep(2 ** attempt)
    raise NetworkUnavailable(
        f"{url}: unavailable after {RETRIES} attempts ({type(last_error).__name__})")


def require_status(result: dict, expected: set[int], label: str) -> None:
    if result["status"] not in expected:
        raise SemanticFailure(f"{label}: HTTP {result['status']}, expected {sorted(expected)}")


def check_document(url: str, path: Path, types: set[str], label: str) -> dict:
    head = request(url)
    get = request(url, method="GET", read_all=True)
    require_status(head, {200}, f"{label} HEAD")
    require_status(get, {200}, f"{label} GET")
    local = path.read_bytes()
    if head["content_type"] not in types or get["content_type"] not in types:
        raise SemanticFailure(f"{label}: content type mismatch")
    if head["content_length"] != len(local) or get["body"] != local:
        raise SemanticFailure(f"{label}: live bytes differ from local artifact")
    return {
        "url": url,
        "final_url": get["final_url"],
        "size_bytes": len(local),
        "sha256": hashlib.sha256(local).hexdigest(),
        "head_status": head["status"],
        "get_status": get["status"],
        "content_type": get["content_type"],
    }


def check_link(url: str, label: str) -> dict:
    try:
        result = request(url)
    except HTTPFailure as error:
        if error.code not in {403, 405, 501}:
            raise
        result = request(url, method="GET", byte_range="bytes=0-0")
    require_status(result, {200, 204, 206}, label)
    return {key: value for key, value in result.items() if key != "body"}


def range_total(result: dict) -> int | None:
    try:
        return int((result.get("content_range") or "").rsplit("/", 1)[1])
    except (IndexError, ValueError):
        return None


def check_asset(url: str, size: int, types: set[str], label: str) -> dict:
    try:
        head = request(url)
        require_status(head, {200}, f"{label} HEAD")
        full_size = head["content_length"]
        content_type = head["content_type"]
        final_url = head["final_url"]
        head_status: int | str = head["status"]
    except HTTPFailure as error:
        if error.code not in {403, 405, 501}:
            raise
        full_size = None
        content_type = None
        final_url = None
        head_status = f"unsupported:{error.code}"
    samples = []
    for position in (0, size - 1):
        result = request(
            url, method="GET", byte_range=f"bytes={position}-{position}", read_all=True)
        require_status(result, {206}, f"{label} byte {position}")
        expected_range = f"bytes {position}-{position}/{size}"
        if result["content_length"] != 1 or len(result["body"]) != 1:
            raise SemanticFailure(f"{label}: byte range length mismatch")
        if result["content_range"] != expected_range or range_total(result) != size:
            raise SemanticFailure(f"{label}: Content-Range mismatch")
        samples.append({
            "status": result["status"],
            "content_range": result["content_range"],
            "byte_hex": result["body"].hex(),
        })
        if full_size is None:
            full_size = range_total(result)
            content_type = result["content_type"]
            final_url = result["final_url"]
    if full_size != size or content_type not in types:
        raise SemanticFailure(f"{label}: full length or content type mismatch")
    return {
        "url": url,
        "final_url": final_url,
        "size_bytes": size,
        "content_type": content_type,
        "head_status": head_status,
        "first_range": samples[0],
        "last_range": samples[1],
    }


def check_release(publication: dict) -> dict:
    expected_doc = json.loads((ROOT / "data" / "release-assets.json").read_text())
    media = publication["media"]
    api_url = (
        f"https://api.github.com/repos/{media['repository']}/releases/tags/"
        f"{media['release_tag']}")
    response = request(api_url, method="GET", read_all=True)
    require_status(response, {200}, "release API")
    try:
        release = json.loads(response["body"])
    except json.JSONDecodeError as error:
        raise SemanticFailure("Release API returned invalid JSON") from error
    if (release.get("tag_name") != media["release_tag"] or release.get("draft")
            or release.get("prerelease")):
        raise SemanticFailure("Release identity/state mismatch")
    expected = {row["name"]: row for row in expected_doc["assets"]}
    actual = {row["name"]: row for row in release.get("assets", [])}
    if set(actual) != set(expected):
        raise SemanticFailure("Release asset inventory mismatch")
    records = []
    for name in sorted(expected):
        wanted, found = expected[name], actual[name]
        if found.get("size") != wanted["size_bytes"] or found.get("state") != "uploaded":
            raise SemanticFailure(f"Release asset state/size mismatch: {name}")
        digest = found.get("digest")
        if digest is not None and digest != f"sha256:{wanted['sha256']}":
            raise SemanticFailure(f"Release asset digest mismatch: {name}")
        records.append({
            "name": name,
            "size_bytes": found["size"],
            "state": found["state"],
            "digest": digest,
            "url": found["browser_download_url"],
        })
    return {"api_url": api_url, "release_url": release["html_url"], "assets": records}


def record_failure(report: dict, operation) -> object | None:
    try:
        return operation()
    except NetworkUnavailable as error:
        report["network_failures"].append(str(error))
    except SemanticFailure as error:
        report["semantic_failures"].append(str(error))
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    publication, episodes = load_catalog()
    report = {
        "schema_version": 1,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "result": "pass",
        "network_failures": [],
        "semantic_failures": [],
        "documents": {},
        "release": None,
        "enclosures": [],
        "master_archive": None,
        "source_links": [],
    }
    documents = (
        ("landing_page", publication["feed"]["site_url"], ROOT / "docs" / "index.html", {"text/html"}),
        ("feed", publication["feed"]["feed_url"], ROOT / "docs" / "feed.xml",
         {"application/rss+xml", "application/xml", "text/xml"}),
        ("artwork", publication["feed"]["artwork_url"], ROOT / "docs" / "cover.jpg", {"image/jpeg"}),
    )
    for name, url, path, types in documents:
        value = record_failure(report, lambda url=url, path=path, types=types, name=name:
                               check_document(url, path, types, name))
        if value is not None:
            report["documents"][name] = value
    report["release"] = record_failure(report, lambda: check_release(publication))

    operations = []
    for episode in episodes:
        operations.append(("enclosure", episode.number, None, lambda episode=episode:
                           check_asset(episode.enclosure_url, episode.size_bytes, MEDIA_TYPES,
                                       f"lecture {episode.number:02d}")))
        for kind, url in (
            ("source_video", episode.source_video_url),
            ("transcript_html", episode.transcript_html_url),
            ("transcript_pdf", episode.transcript_pdf_url),
        ):
            operations.append(("source", episode.number, kind,
                               lambda number=episode.number, kind=kind, url=url:
                               check_link(url, f"lecture {number:02d} {kind}")))
    release_assets = json.loads((ROOT / "data" / "release-assets.json").read_text())
    master = next(row for row in release_assets["assets"] if row["role"] == "master_archive")
    operations.append(("master", 0, None, lambda: check_asset(
        publication["media"]["base_url"] + master["name"], master["size_bytes"],
        {"application/zip", "application/octet-stream"}, "master archive")))

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        futures = {executor.submit(call): (category, number, kind)
                   for category, number, kind, call in operations}
        for future in concurrent.futures.as_completed(futures):
            category, number, kind = futures[future]
            value = record_failure(report, future.result)
            if value is None:
                continue
            if category == "enclosure":
                report["enclosures"].append({"lecture": number, **value})
            elif category == "master":
                report["master_archive"] = value
            else:
                report["source_links"].append({"lecture": number, "kind": kind, **value})
    report["enclosures"].sort(key=lambda row: row["lecture"])
    report["source_links"].sort(key=lambda row: (row["lecture"], row["kind"]))
    if report["semantic_failures"]:
        report["result"], exit_code = "semantic_failure", 1
    elif report["network_failures"]:
        report["result"], exit_code = "network_unavailable", 2
    else:
        exit_code = 0
    if args.output:
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "result": report["result"],
        "documents": len(report["documents"]),
        "release_assets": len(report["release"]["assets"]) if report["release"] else 0,
        "enclosures": len(report["enclosures"]),
        "master_archive": report["master_archive"] is not None,
        "source_links": len(report["source_links"]),
        "network_failures": len(report["network_failures"]),
        "semantic_failures": len(report["semantic_failures"]),
    }, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
