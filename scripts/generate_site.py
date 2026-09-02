#!/usr/bin/env python3
"""Regenerate or check the deterministic GitHub Pages output."""

from __future__ import annotations

import argparse
import sys

from feedlib import outputs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if committed output differs")
    args = parser.parse_args()
    failures: list[str] = []
    for path, expected in outputs().items():
        if args.check:
            if not path.is_file() or path.read_bytes() != expected:
                failures.append(str(path))
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(expected)
            print(f"wrote {path}")
    if failures:
        print("generated output is stale: " + ", ".join(failures), file=sys.stderr)
        return 1
    if args.check:
        print("PASS deterministic generated output")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
