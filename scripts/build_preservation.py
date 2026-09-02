#!/usr/bin/env python3
"""Build a deterministic canonical CS229 preservation ZIP outside Git."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import zipfile
from pathlib import Path

from feedlib import ROOT, load_catalog

PACKAGE_NAME = "stanford-cs229-machine-learning-audio-edition-v1.0"
ZIP_NAME = f"{PACKAGE_NAME}.zip"
FIXED_ZIP_TIME = (1980, 1, 1, 0, 0, 0)
ZIP_ASSET_LIMIT = 2 * 1024 * 1024 * 1024
DOCUMENT_NAMES = ("README.md", "LICENSE.md", "PROVENANCE.md")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def probe(path: Path, ffprobe: str) -> dict:
    result = subprocess.run(
        [
            ffprobe, "-v", "error", "-show_entries",
            "format=format_name,duration,size,bit_rate:format_tags:"
            "stream=index,codec_type,codec_name,profile,sample_rate,channels,bit_rate:stream_tags",
            "-of", "json", str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def canonical_tags(number: int, title: str) -> dict[str, str]:
    return {
        "album": "CS229 — Machine Learning",
        "album_artist": "Stanford Engineering Everywhere",
        "artist": "Andrew Ng",
        "comment": "Unofficial audio-only adaptation; source and licence in NOTICE.md",
        "genre": "Education",
        "title": f"Lecture {number:02d} — {title}",
        "track": f"{number}/20",
    }


def manifest_record(episode, source: Path, destination_name: str, ffprobe: str) -> dict:
    if not source.is_file() or source.is_symlink():
        raise ValueError(f"Missing or non-regular source media: {source}")
    actual_hash = sha256(source)
    if source.stat().st_size != episode.size_bytes or actual_hash != episode.sha256:
        raise ValueError(f"Authoritative size/hash mismatch: {source.name}")
    data = probe(source, ffprobe)
    streams = [stream for stream in data.get("streams", []) if stream.get("codec_type") == "audio"]
    if len(streams) != 1:
        raise ValueError(f"Expected exactly one audio stream: {source.name}")
    stream = streams[0]
    expected_signature = ("aac", "LC", "48000", 2)
    signature = (
        stream.get("codec_name"), stream.get("profile"),
        stream.get("sample_rate"), stream.get("channels"),
    )
    if signature != expected_signature:
        raise ValueError(f"Unexpected audio signature for {source.name}: {signature}")
    media_format = data.get("format", {})
    if "m4a" not in media_format.get("format_name", "").split(","):
        raise ValueError(f"Unexpected container for {source.name}")
    if abs(float(media_format["duration"]) - episode.duration_seconds) >= 0.001:
        raise ValueError(f"Duration mismatch for {source.name}")
    tags = media_format.get("tags", {})
    for name, value in canonical_tags(episode.number, episode.title).items():
        if tags.get(name) != value:
            raise ValueError(f"Embedded tag {name!r} mismatch for {source.name}")
    return {
        "lecture": episode.number,
        "title": episode.title,
        "source_staging_filename": source.name,
        "canonical_filename": destination_name,
        "package_path": f"audio/{destination_name}",
        "size_bytes": episode.size_bytes,
        "sha256": actual_hash,
        "duration_seconds": episode.duration_seconds,
        "container": {
            "format_name": media_format["format_name"],
            "average_bit_rate_bps": int(media_format["bit_rate"]),
        },
        "audio": {
            "codec": "aac",
            "profile": "LC",
            "sample_rate_hz": 48000,
            "channels": 2,
            "nominal_bit_rate_bps": int(stream["bit_rate"]),
        },
        "embedded_tags": {name: tags[name] for name in sorted(canonical_tags(episode.number, episode.title))},
        "source_video_url": episode.source_video_url,
        "transcript_html_url": episode.transcript_html_url,
        "transcript_pdf_url": episode.transcript_pdf_url,
        "extraction": {
            "method": "FFmpeg stream copy/remux",
            "command_audio_options": "-map 0:a:0 -vn -c:a copy -movflags +faststart",
            "transcoded": False,
            "evidence_limit": "Source videos were remotely probed and size-checked but not retained for packet-level comparison.",
        },
    }


def zip_info(name: str, directory: bool = False) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, FIXED_ZIP_TIME)
    info.create_system = 3
    info.compress_type = zipfile.ZIP_STORED
    info.external_attr = ((0o40755 if directory else 0o100644) << 16) | (0x10 if directory else 0)
    info.internal_attr = 0
    info.extra = b""
    info.comment = b""
    return info


def build_zip(package_root: Path, destination: Path) -> None:
    root = package_root.name
    ordered = [
        *[f"audio/CS229-lecture{number:02d}.m4a" for number in range(1, 21)],
        "SHA256SUMS", "README.md", "LICENSE.md", "PROVENANCE.md", "MANIFEST.json",
    ]
    with zipfile.ZipFile(destination, "w", allowZip64=True) as archive:
        archive.writestr(zip_info(f"{root}/", directory=True), b"")
        archive.writestr(zip_info(f"{root}/audio/", directory=True), b"")
        for relative in ordered:
            path = package_root / relative
            with path.open("rb") as source, archive.open(zip_info(f"{root}/{relative}"), "w") as output:
                shutil.copyfileobj(source, output, length=1024 * 1024)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--media-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--ffprobe", default="ffprobe")
    args = parser.parse_args()
    media_dir = args.media_dir.resolve()
    output_dir = args.output_dir.resolve()
    if output_dir == ROOT or ROOT in output_dir.parents:
        raise ValueError("Preservation output must be outside the Git repository")
    package_root = output_dir / PACKAGE_NAME
    archive_path = output_dir / ZIP_NAME
    sidecar_path = output_dir / f"{ZIP_NAME}.sha256"
    report_path = output_dir / "build-report.json"
    for path in (package_root, archive_path, sidecar_path, report_path):
        if path.exists() or path.is_symlink():
            raise FileExistsError(f"Refusing to overwrite existing output: {path}")
    output_dir.mkdir(parents=True, exist_ok=True)
    (package_root / "audio").mkdir(parents=True)

    _, episodes = load_catalog()
    records = []
    for episode in episodes:
        source = media_dir / episode.source_filename
        name = f"CS229-lecture{episode.number:02d}.m4a"
        record = manifest_record(episode, source, name, args.ffprobe)
        destination = package_root / "audio" / name
        shutil.copyfile(source, destination)
        if sha256(destination) != record["sha256"]:
            raise RuntimeError(f"Copied audio hash mismatch: {name}")
        records.append(record)
        print(f"PASS source and copy {name}")

    for name in DOCUMENT_NAMES:
        shutil.copyfile(ROOT / "preservation" / name, package_root / name)

    manifest = {
        "schema_version": 1,
        "edition": {
            "name": "Stanford CS229 Machine Learning — Unofficial Audio Preservation Edition",
            "version": "1.0",
            "package_name": PACKAGE_NAME,
            "non_commercial": True,
            "unofficial": True,
            "endorsed_by_stanford_or_andrew_ng": False,
        },
        "course": {
            "code": "CS229",
            "title": "Machine Learning",
            "lecturer": "Andrew Ng",
            "source_publisher": "Stanford Engineering Everywhere",
            "source_term": "Autumn 2007",
            "course_url": "https://see.stanford.edu/Course/CS229",
        },
        "license": {
            "identifier": "CC-BY-NC-SA-4.0",
            "url": "https://creativecommons.org/licenses/by-nc-sa/4.0/legalcode",
            "source_policy_url": "https://see.stanford.edu/UsingSEE",
            "source_policy_access_date": "2026-09-02",
        },
        "media_count": len(records),
        "aggregate_media_size_bytes": sum(record["size_bytes"] for record in records),
        "records": records,
        "checksum_policy": "SHA256SUMS covers every audio and supporting file except SHA256SUMS itself.",
        "archive_reproducibility": {
            "entry_order": "fixed by scripts/build_preservation.py",
            "entry_timestamp": "1980-01-01T00:00:00 (ZIP epoch; timezone-independent)",
            "entry_permissions": "directories 0755; regular files 0644",
            "compression": "ZIP_STORED for every entry; audio is never recompressed",
            "host_metadata": "excluded",
        },
    }
    manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
    (package_root / "MANIFEST.json").write_bytes(manifest_bytes)

    checksum_paths = [
        *[Path("audio") / f"CS229-lecture{number:02d}.m4a" for number in range(1, 21)],
        Path("README.md"), Path("LICENSE.md"), Path("PROVENANCE.md"), Path("MANIFEST.json"),
    ]
    sums = "".join(f"{sha256(package_root / relative)}  {relative.as_posix()}\n" for relative in checksum_paths)
    (package_root / "SHA256SUMS").write_text(sums, encoding="utf-8", newline="\n")

    build_zip(package_root, archive_path)
    archive_hash = sha256(archive_path)
    sidecar_path.write_text(f"{archive_hash}  {ZIP_NAME}\n", encoding="utf-8", newline="\n")
    report = {
        "result": "pass",
        "package": PACKAGE_NAME,
        "archive": ZIP_NAME,
        "archive_size_bytes": archive_path.stat().st_size,
        "archive_sha256": archive_hash,
        "below_github_2_gib_asset_limit": archive_path.stat().st_size < ZIP_ASSET_LIMIT,
        "media_files": len(records),
        "media_size_bytes": sum(record["size_bytes"] for record in records),
    }
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
