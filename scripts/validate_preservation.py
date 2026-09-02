#!/usr/bin/env python3
"""Independently validate and extract a canonical CS229 preservation ZIP."""

from __future__ import annotations

import argparse
import hashlib
import json
import stat
import zipfile
from pathlib import Path, PurePosixPath

from build_preservation import FIXED_ZIP_TIME, PACKAGE_NAME, ZIP_ASSET_LIMIT, ZIP_NAME
from feedlib import ROOT


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def expected_names() -> list[str]:
    root = PACKAGE_NAME
    return [
        f"{root}/", f"{root}/audio/",
        *[f"{root}/audio/CS229-lecture{number:02d}.m4a" for number in range(1, 21)],
        f"{root}/SHA256SUMS", f"{root}/README.md", f"{root}/LICENSE.md",
        f"{root}/PROVENANCE.md", f"{root}/MANIFEST.json",
    ]


def safe_name(name: str) -> bool:
    path = PurePosixPath(name)
    return not path.is_absolute() and ".." not in path.parts and "" not in path.parts


def parse_sums(path: Path) -> dict[str, str]:
    result = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        digest, relative = line.split("  ", 1)
        if len(digest) != 64 or relative in result:
            raise ValueError("Malformed or duplicate SHA256SUMS entry")
        result[relative] = digest
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--tree", type=Path, required=True)
    parser.add_argument("--extract-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    archive = args.archive.resolve()
    tree = args.tree.resolve()
    extract_dir = args.extract_dir.resolve()
    report_path = args.report.resolve()
    if extract_dir == ROOT or ROOT in extract_dir.parents:
        raise ValueError("Extraction output must be outside the Git repository")
    if report_path == ROOT or ROOT in report_path.parents:
        raise ValueError("Validation report must be outside the Git repository")
    if extract_dir.exists() or extract_dir.is_symlink():
        raise FileExistsError(f"Refusing to extract over existing path: {extract_dir}")
    if report_path.exists() or report_path.is_symlink():
        raise FileExistsError(f"Refusing to overwrite report: {report_path}")
    if archive.name != ZIP_NAME or tree.name != PACKAGE_NAME:
        raise ValueError("Unexpected archive or package-tree name")
    if not archive.is_file() or archive.is_symlink():
        raise ValueError("Archive is missing or non-regular")

    with zipfile.ZipFile(archive) as package:
        infos = package.infolist()
        names = [info.filename for info in infos]
        if names != expected_names() or len(names) != len(set(names)):
            raise ValueError("Archive inventory/order mismatch")
        if package.testzip() is not None:
            raise ValueError("Archive CRC validation failed")
        if package.comment:
            raise ValueError("Archive has an unexpected comment")
        for info in infos:
            if not safe_name(info.filename) or info.date_time != FIXED_ZIP_TIME:
                raise ValueError(f"Unsafe or non-deterministic entry: {info.filename}")
            if info.flag_bits & 0x1 or info.extra or info.comment:
                raise ValueError(f"Encrypted or metadata-bearing entry: {info.filename}")
            if info.extract_version > 20:
                raise ValueError(f"Entry unnecessarily requires newer ZIP features: {info.filename}")
            mode = info.external_attr >> 16
            if info.is_dir():
                if not stat.S_ISDIR(mode) or stat.S_IMODE(mode) != 0o755:
                    raise ValueError(f"Directory mode mismatch: {info.filename}")
            elif not stat.S_ISREG(mode) or stat.S_IMODE(mode) != 0o644:
                raise ValueError(f"Non-regular entry or mode mismatch: {info.filename}")
            if info.compress_type != zipfile.ZIP_STORED:
                raise ValueError(f"Entry is not stored: {info.filename}")
        package.extractall(extract_dir)

    extracted = extract_dir / PACKAGE_NAME
    tree_files = sorted(path.relative_to(tree) for path in tree.rglob("*") if path.is_file())
    extracted_files = sorted(path.relative_to(extracted) for path in extracted.rglob("*") if path.is_file())
    if tree_files != extracted_files:
        raise ValueError("Extracted file set does not match authoritative build tree")
    for relative in tree_files:
        original = tree / relative
        restored = extracted / relative
        if original.stat().st_size != restored.stat().st_size or sha256(original) != sha256(restored):
            raise ValueError(f"Extracted file mismatch: {relative}")

    sums = parse_sums(extracted / "SHA256SUMS")
    expected_sum_paths = {path.as_posix() for path in extracted_files if path.as_posix() != "SHA256SUMS"}
    if set(sums) != expected_sum_paths:
        raise ValueError("SHA256SUMS coverage mismatch")
    for relative, digest in sums.items():
        if sha256(extracted / relative) != digest:
            raise ValueError(f"Internal checksum mismatch: {relative}")

    manifest = json.loads((extracted / "MANIFEST.json").read_text(encoding="utf-8"))
    if manifest.get("edition", {}).get("name") != (
            "CS229 Machine Learning — Unofficial Audio Preservation Edition"):
        raise ValueError("Manifest edition title mismatch")
    if manifest.get("media_count") != 20 or manifest.get("aggregate_media_size_bytes") != 1_798_240_224:
        raise ValueError("Manifest collection totals mismatch")
    if [row.get("lecture") for row in manifest.get("records", [])] != list(range(1, 21)):
        raise ValueError("Manifest lecture sequence mismatch")
    for number, row in enumerate(manifest["records"], start=1):
        relative = f"audio/CS229-lecture{number:02d}.m4a"
        audio_path = extracted / relative
        if (row.get("canonical_filename") != audio_path.name
                or row.get("package_path") != relative
                or row.get("size_bytes") != audio_path.stat().st_size
                or row.get("sha256") != sha256(audio_path)):
            raise ValueError(f"Manifest media identity mismatch: lecture {number:02d}")
    sidecar = archive.with_name(f"{archive.name}.sha256")
    sidecar_digest, sidecar_name = sidecar.read_text(encoding="utf-8").strip().split("  ", 1)
    archive_digest = sha256(archive)
    if sidecar_name != archive.name or sidecar_digest != archive_digest:
        raise ValueError("External archive checksum mismatch")

    report = {
        "result": "pass",
        "archive": archive.name,
        "archive_size_bytes": archive.stat().st_size,
        "archive_sha256": archive_digest,
        "below_github_2_gib_asset_limit": archive.stat().st_size < ZIP_ASSET_LIMIT,
        "zip_entries": len(expected_names()),
        "regular_files": len(tree_files),
        "audio_files": 20,
        "media_size_bytes": manifest["aggregate_media_size_bytes"],
        "crc_test": "pass",
        "safe_paths_and_types": "pass",
        "fixed_metadata": "pass",
        "internal_sha256s": "pass",
        "extracted_tree_comparison": "pass",
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
