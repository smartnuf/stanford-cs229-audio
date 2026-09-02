#!/usr/bin/env python3
"""Generate the deterministic GitHub Release asset manifest from a package build."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from build_preservation import DOCUMENT_NAMES, PACKAGE_NAME, ZIP_NAME


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    build_dir = args.build_dir.resolve()
    package = build_dir / PACKAGE_NAME
    assets = []
    for number in range(1, 21):
        name = f"CS229-lecture{number:02d}.m4a"
        assets.append((name, package / "audio" / name, "podcast_enclosure"))
    assets.extend([
        (ZIP_NAME, build_dir / ZIP_NAME, "master_archive"),
        (f"{ZIP_NAME}.sha256", build_dir / f"{ZIP_NAME}.sha256", "master_checksum"),
        ("MANIFEST.json", package / "MANIFEST.json", "metadata"),
        ("SHA256SUMS", package / "SHA256SUMS", "checksums"),
        *((name, package / name, "documentation") for name in DOCUMENT_NAMES),
    ])
    if any(not path.is_file() or path.is_symlink() for _, path, _ in assets):
        raise ValueError("Release source inventory contains a missing or non-regular file")
    document = {
        "schema_version": 1,
        "repository": "smartnuf/stanford-cs229-audio",
        "tag": "audio-v1.0.0",
        "asset_count": len(assets),
        "assets": [
            {"name": name, "role": role, "size_bytes": path.stat().st_size, "sha256": sha256(path)}
            for name, path, role in assets
        ],
    }
    rendered = json.dumps(document, indent=2, sort_keys=True) + "\n"
    if args.output.exists() and args.output.read_text(encoding="utf-8") == rendered:
        print(f"unchanged {args.output}")
    else:
        args.output.write_text(rendered, encoding="utf-8", newline="\n")
        print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
