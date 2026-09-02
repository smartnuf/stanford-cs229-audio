#!/usr/bin/env python3
"""Prepare the exact Zenodo draft file bundle outside Git without publishing it."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

from build_preservation import DOCUMENT_NAMES, PACKAGE_NAME, ZIP_NAME
from feedlib import ROOT


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    build = args.build_dir.resolve()
    output = args.output_dir.resolve()
    report_path = args.report.resolve()
    for label, path in (("build", build), ("output", output), ("report", report_path)):
        if path == ROOT or ROOT in path.parents:
            raise ValueError(f"Zenodo {label} path must be outside the Git repository")
    if report_path == output or output in report_path.parents:
        raise ValueError("Zenodo report must be outside the upload directory")
    if output.exists() or output.is_symlink():
        raise FileExistsError(f"Refusing to overwrite Zenodo bundle: {output}")
    if report_path.exists() or report_path.is_symlink():
        raise FileExistsError(f"Refusing to overwrite Zenodo report: {report_path}")
    package = build / PACKAGE_NAME
    release_sources = [
        *((package / "audio" / f"CS229-lecture{number:02d}.m4a",
           f"CS229-lecture{number:02d}.m4a") for number in range(1, 21)),
        (build / ZIP_NAME, ZIP_NAME),
        (build / f"{ZIP_NAME}.sha256", f"{ZIP_NAME}.sha256"),
        (package / "MANIFEST.json", "MANIFEST.json"),
        (package / "SHA256SUMS", "SHA256SUMS"),
        *((package / name, name) for name in DOCUMENT_NAMES),
    ]
    contract = json.loads((ROOT / "data" / "release-assets.json").read_text(encoding="utf-8"))
    expected = {row["name"]: row for row in contract["assets"]}
    actual_names = {name for _, name in release_sources}
    if contract.get("asset_count") != 27 or actual_names != set(expected):
        raise ValueError("Canonical release contract inventory mismatch")
    if any(not source.is_file() or source.is_symlink() for source, _ in release_sources):
        raise ValueError("Canonical build contains a missing or non-regular release source")
    for source, name in release_sources:
        row = expected[name]
        if source.stat().st_size != row["size_bytes"] or sha256(source) != row["sha256"]:
            raise ValueError(f"Build does not match canonical release contract: {name}")
    sources = [
        *release_sources[20:],
        (ROOT / "zenodo" / "metadata.json", "ZENODO-METADATA.json"),
    ]
    if any(not source.is_file() or source.is_symlink() for source, _ in sources):
        raise ValueError("Zenodo source inventory contains a missing or non-regular file")
    output.mkdir(parents=True)
    for source, name in sources:
        shutil.copyfile(source, output / name)
    report = {
        "result": "pass",
        "publication_state": "local_bundle_only_not_published",
        "canonical_release_contract": "data/release-assets.json",
        "file_count": len(sources),
        "files": [
            {
                "name": name,
                "size_bytes": (output / name).stat().st_size,
                "sha256": sha256(output / name),
            }
            for _, name in sources
        ],
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
