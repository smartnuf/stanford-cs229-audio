#!/usr/bin/env python3
"""Reject forbidden or oversized blobs and personal author emails in reachable Git history."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from validate_repo import (
    FORBIDDEN_NAMES, FORBIDDEN_SUFFIXES, MAX_TRACKED_BYTES, ROOT, SECRET_PATTERNS,
)

ALLOWED_EMAIL_SUFFIXES = ("@users.noreply.github.com", "@cs229-preservation.invalid")


def git(*arguments: str, input_bytes: bytes | None = None) -> bytes:
    return subprocess.run(
        ["git", *arguments], cwd=ROOT, input=input_bytes, check=True, capture_output=True,
    ).stdout


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--revision", metavar="REV",
        help="audit this commit and all ancestors; default: every local ref",
    )
    args = parser.parse_args(argv)
    try:
        if git("rev-parse", "--is-shallow-repository").strip() == b"true":
            print("FAIL: full Git history is required (shallow repository)", file=sys.stderr)
            return 1
        revisions = ("--all",)
        if args.revision is not None:
            commit = git("rev-parse", "--verify", "--end-of-options",
                         args.revision + "^{commit}").decode().strip()
            revisions = (commit,)
    except subprocess.CalledProcessError:
        print("FAIL: audit revision must resolve to an available commit", file=sys.stderr)
        return 1
    failures: list[str] = []
    objects = git("rev-list", "--objects", *revisions).decode().splitlines()
    blobs = 0
    for row in objects:
        object_id, _, path_text = row.partition(" ")
        if git("cat-file", "-t", object_id).strip() != b"blob":
            continue
        blobs += 1
        path = Path(path_text)
        size = int(git("cat-file", "-s", object_id))
        lower = path.name.lower()
        if size >= MAX_TRACKED_BYTES:
            failures.append(f"oversized blob: {path}")
        if path.suffix.lower() in FORBIDDEN_SUFFIXES:
            failures.append(f"forbidden blob type: {path}")
        if lower in FORBIDDEN_NAMES or lower == ".env" or lower.startswith(".env."):
            failures.append(f"credential/config filename: {path}")
        content = git("cat-file", "blob", object_id)
        if any(pattern.search(content) for pattern in SECRET_PATTERNS):
            failures.append(f"credential signature in blob: {path}")

    emails = set(git("log", "--format=%ae%n%ce", *revisions).decode().splitlines())
    for email in emails:
        if email and not email.endswith(ALLOWED_EMAIL_SUFFIXES):
            failures.append("unapproved public author/committer email in reachable history")
    if failures:
        for failure in sorted(set(failures)):
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print(f"PASS reachable Git history: {blobs} blobs, {len(emails)} non-contact author email(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
