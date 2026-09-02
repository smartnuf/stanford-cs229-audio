#!/usr/bin/env python3
"""Bounded read-only checks for Pages, releases, Zenodo, and Stanford links."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import socket
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from feedlib import ROOT, load_catalog

USER_AGENT = "stanford-cs229-audio-integrity/1.0"
RETRIES = 3
TIMEOUT = 15
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
                    "last_modified": response.headers.get("Last-Modified"),
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


def check_document(url: str, path: Path, types: set[str], label: str,
                   require_last_modified: bool = False) -> dict:
    head = request(url)
    get = request(url, method="GET", read_all=True)
    require_status(head, {200}, f"{label} HEAD")
    require_status(get, {200}, f"{label} GET")
    local = path.read_bytes()
    if head["content_type"] not in types or get["content_type"] not in types:
        raise SemanticFailure(f"{label}: content type mismatch")
    if head["content_length"] != len(local) or get["body"] != local:
        raise SemanticFailure(f"{label}: live bytes differ from local artifact")
    if require_last_modified and not head["last_modified"]:
        raise SemanticFailure(f"{label}: HEAD response lacks Last-Modified")
    return {
        "url": url,
        "final_url": get["final_url"],
        "size_bytes": len(local),
        "sha256": hashlib.sha256(local).hexdigest(),
        "head_status": head["status"],
        "get_status": get["status"],
        "content_type": get["content_type"],
        "last_modified": head["last_modified"],
    }


def check_link(url: str, label: str, expected_types: set[str] | None = None) -> dict:
    try:
        result = request(url)
    except HTTPFailure as error:
        if error.code not in {403, 405, 501}:
            raise
        result = request(url, method="GET", byte_range="bytes=0-0")
    require_status(result, {200, 204, 206}, label)
    if expected_types and result["content_type"] not in expected_types:
        raise SemanticFailure(f"{label}: content type mismatch: {result['content_type']}")
    return {key: value for key, value in result.items() if key != "body"}


def range_total(result: dict) -> int | None:
    try:
        return int((result.get("content_range") or "").rsplit("/", 1)[1])
    except (IndexError, ValueError):
        return None


def check_asset(url: str, size: int, types: set[str], label: str) -> dict:
    head = request(url)
    require_status(head, {200}, f"{label} HEAD")
    full_size = head["content_length"]
    content_type = head["content_type"]
    final_url = head["final_url"]
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
    if full_size != size or content_type not in types:
        raise SemanticFailure(
            f"{label}: HEAD length/type mismatch ({full_size}, {content_type})")
    return {
        "url": url,
        "final_url": final_url,
        "size_bytes": size,
        "content_type": content_type,
        "head_status": head["status"],
        "first_range": samples[0],
        "last_range": samples[1],
    }


def resolve_tag_commit(repository: str, tag: str) -> tuple[str, list[dict]]:
    base = f"https://api.github.com/repos/{repository}"
    response = request(f"{base}/git/ref/tags/{quote(tag, safe='')}", method="GET", read_all=True)
    require_status(response, {200}, "release tag ref")
    record = json.loads(response["body"])
    target = record.get("object", {})
    chain = [{"type": target.get("type"), "sha": target.get("sha")}]
    for _ in range(4):
        if target.get("type") == "commit":
            return target["sha"], chain
        if target.get("type") != "tag" or not target.get("sha"):
            break
        response = request(f"{base}/git/tags/{target['sha']}", method="GET", read_all=True)
        require_status(response, {200}, "annotated tag object")
        target = json.loads(response["body"]).get("object", {})
        chain.append({"type": target.get("type"), "sha": target.get("sha")})
    raise SemanticFailure("Release tag does not resolve to a commit")


def check_release(publication: dict, expected_release_commit: str) -> dict:
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
            or release.get("prerelease") or release.get("html_url") != media["release_url"]):
        raise SemanticFailure("Release identity/state mismatch")
    if release.get("immutable") is not True:
        raise SemanticFailure("Release is not immutable")
    tag_commit, tag_chain = resolve_tag_commit(media["repository"], media["release_tag"])
    if tag_commit != expected_release_commit:
        raise SemanticFailure(
            f"Release tag target {tag_commit} does not match expected release commit "
            f"{expected_release_commit}")
    expected = {row["name"]: row for row in expected_doc["assets"]}
    actual = {row["name"]: row for row in release.get("assets", [])}
    if set(actual) != set(expected):
        raise SemanticFailure("Release asset inventory mismatch")
    records = []
    for name in sorted(expected):
        wanted, found = expected[name], actual[name]
        if found.get("size") != wanted["size_bytes"] or found.get("state") != "uploaded":
            raise SemanticFailure(f"Release asset state/size mismatch: {name}")
        if (wanted["role"] == "podcast_enclosure"
                and found.get("content_type") not in {"audio/mp4", "audio/x-m4a"}):
            raise SemanticFailure(f"Release API enclosure content type mismatch: {name}")
        if wanted["role"] == "master_archive" and found.get("content_type") != "application/zip":
            raise SemanticFailure("Release API master archive content type mismatch")
        digest = found.get("digest")
        if digest != f"sha256:{wanted['sha256']}":
            raise SemanticFailure(f"Release asset digest mismatch: {name}")
        expected_url = media["base_url"] + name
        if found.get("browser_download_url") != expected_url:
            raise SemanticFailure(f"Release asset URL mismatch: {name}")
        records.append({
            "name": name,
            "size_bytes": found["size"],
            "state": found["state"],
            "digest": digest,
            "content_type": found.get("content_type"),
            "url": found["browser_download_url"],
        })
    return {
        "api_url": api_url,
        "release_url": release["html_url"],
        "immutable": True,
        "expected_release_commit": expected_release_commit,
        "resolved_tag_commit": tag_commit,
        "tag_chain": tag_chain,
        "assets": records,
    }


def check_zenodo(publication: dict) -> dict:
    expected = json.loads((ROOT / "data" / "zenodo-record.json").read_text())
    preservation = publication["preservation"]
    response = request(expected["api_url"], method="GET", read_all=True)
    require_status(response, {200}, "Zenodo record API")
    try:
        record = json.loads(response["body"])
    except json.JSONDecodeError as error:
        raise SemanticFailure("Zenodo record API returned invalid JSON") from error
    metadata = record.get("metadata", {})
    licence = metadata.get("license", {})
    creators = [{key: value for key, value in row.items() if value is not None}
                for row in metadata.get("creators", [])]
    if (record.get("id") != expected["record_id"]
            or record.get("doi") != expected["doi"]
            or metadata.get("title") != publication["feed"]["title"]
            or creators != [{"name": "smartnuf"}]
            or not isinstance(licence, dict)
            or licence.get("id") != publication["license"]["identifier"]):
        raise SemanticFailure("Zenodo public identity/metadata mismatch")
    expected_files = {row["name"]: row for row in expected["files"]}
    actual_files = {row.get("key"): row for row in record.get("files", [])}
    if set(actual_files) != set(expected_files):
        raise SemanticFailure("Zenodo public file inventory mismatch")
    files = []
    master = None
    for name in [row["name"] for row in expected["files"]]:
        wanted, found = expected_files[name], actual_files[name]
        url = found.get("links", {}).get("self")
        if (found.get("size") != wanted["size_bytes"]
                or found.get("checksum") != f"md5:{wanted['md5']}"
                or url != wanted["url"]):
            raise SemanticFailure(f"Zenodo public file metadata mismatch: {name}")
        if name.endswith(".zip"):
            master = check_asset(
                url, wanted["size_bytes"], {"application/zip", "application/octet-stream"},
                "Zenodo master archive")
        else:
            head = request(url)
            require_status(head, {200}, f"Zenodo {name} HEAD")
            if head["content_length"] != wanted["size_bytes"]:
                raise SemanticFailure(f"Zenodo public file length mismatch: {name}")
            files.append({
                "name": name,
                "url": url,
                "size_bytes": wanted["size_bytes"],
                "sha256": wanted["sha256"],
                "md5": wanted["md5"],
                "head_status": head["status"],
                "content_type": head["content_type"],
            })
    doi = request(preservation["doi_url"], method="GET")
    require_status(doi, {200}, "Zenodo DOI resolution")
    if doi["final_url"].rstrip("/") != preservation["record_url"]:
        raise SemanticFailure("Zenodo DOI does not resolve to the pinned record")
    return {
        "record_id": expected["record_id"],
        "record_url": preservation["record_url"],
        "doi": preservation["doi"],
        "doi_url": preservation["doi_url"],
        "api_status": response["status"],
        "doi_status": doi["status"],
        "files": files,
        "master_archive": master,
    }


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
    parser.add_argument("--expected-release-commit")
    args = parser.parse_args()
    publication, episodes = load_catalog()
    expected_release_commit = (
        args.expected_release_commit or publication["media"].get("release_commit"))
    if (not isinstance(expected_release_commit, str) or len(expected_release_commit) != 40
            or any(character not in "0123456789abcdef" for character in expected_release_commit)):
        parser.error("provide --expected-release-commit or pin media.release_commit as a full SHA")
    report = {
        "schema_version": 1,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "checked_out_commit": subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
            capture_output=True, text=True).stdout.strip(),
        "expected_release_commit": expected_release_commit,
        "result": "pass",
        "network_failures": [],
        "semantic_failures": [],
        "compatibility_warnings": [],
        "documents": {},
        "release": None,
        "zenodo": None,
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
                               check_document(url, path, types, name,
                                              require_last_modified=name == "artwork"))
        if value is not None:
            report["documents"][name] = value
    report["release"] = record_failure(
        report, lambda: check_release(publication, expected_release_commit))
    report["zenodo"] = record_failure(report, lambda: check_zenodo(publication))

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
                               check_link(
                                   url, f"lecture {number:02d} {kind}",
                                   {"text/html"} if kind == "transcript_html" else None)))
    release_assets = json.loads((ROOT / "data" / "release-assets.json").read_text())
    master = next(row for row in release_assets["assets"] if row["role"] == "master_archive")
    operations.append(("master", 0, None, lambda: check_asset(
        publication["media"]["base_url"] + master["name"], master["size_bytes"],
        {"application/zip", "application/octet-stream"}, "master archive")))

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
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
    generic_enclosures = [row["lecture"] for row in report["enclosures"]
                            if row["content_type"] == "application/octet-stream"]
    if generic_enclosures:
        report["compatibility_warnings"].append({
            "code": "github_cdn_generic_enclosure_content_type",
            "severity": "P3",
            "lectures": generic_enclosures,
            "message": (
                "GitHub CDN serves these verified M4A assets as application/octet-stream; "
                "release API and RSS metadata remain audio/mp4. Complete the documented "
                "manual iPhone streaming/seeking/downloading test."),
        })
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
        "zenodo_files": (len(report["zenodo"]["files"]) + 1) if report["zenodo"] else 0,
        "enclosures": len(report["enclosures"]),
        "master_archive": report["master_archive"] is not None,
        "source_links": len(report["source_links"]),
        "network_failures": len(report["network_failures"]),
        "semantic_failures": len(report["semantic_failures"]),
        "compatibility_warnings": len(report["compatibility_warnings"]),
    }, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
