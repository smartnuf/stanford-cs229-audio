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
    args = parser.parse_args()
    build = args.build_dir.resolve()
    output = args.output_dir.resolve()
    if output.exists() or output.is_symlink():
        raise FileExistsError(f"Refusing to overwrite Zenodo bundle: {output}")
    output.mkdir(parents=True)
    package = build / PACKAGE_NAME
    sources = [
        (build / ZIP_NAME, ZIP_NAME),
        (build / f"{ZIP_NAME}.sha256", f"{ZIP_NAME}.sha256"),
        (package / "MANIFEST.json", "MANIFEST.json"),
        (package / "SHA256SUMS", "SHA256SUMS"),
        *((package / name, name) for name in DOCUMENT_NAMES),
        (ROOT / "zenodo" / "metadata.json", "ZENODO-METADATA.json"),
    ]
    if any(not source.is_file() or source.is_symlink() for source, _ in sources):
        raise ValueError("Zenodo source inventory contains a missing or non-regular file")
    for source, name in sources:
        shutil.copyfile(source, output / name)
    report = {
        "result": "pass",
        "publication_state": "local_bundle_only_not_published",
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
    (output / "deposit-report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
