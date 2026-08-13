#!/usr/bin/env python3
"""Compatibility entry point for the unified Overte project test profiles."""

from __future__ import annotations

import argparse
from pathlib import Path

from run_tests import main as unified_main


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=("quick", "full"), default="quick")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--suite", action="append", default=[])
    parser.add_argument("--timeout", type=int)
    parser.add_argument("--junit", type=Path)
    parser.add_argument("--fail-fast", action="store_true")
    parser.add_argument("--native-build-dir", type=Path)
    args = parser.parse_args()
    forwarded = ["--profile", f"project-{args.profile}"]
    for suite in args.suite:
        forwarded.extend(("--suite", suite))
    if args.timeout is not None:
        forwarded.extend(("--timeout", str(args.timeout)))
    if args.junit:
        forwarded.extend(("--junit", str(args.junit)))
    if args.native_build_dir:
        forwarded.extend(("--native-build-dir", str(args.native_build_dir)))
    if args.list:
        forwarded.append("--list")
    if args.fail_fast:
        forwarded.append("--fail-fast")
    return unified_main(forwarded)


if __name__ == "__main__":
    raise SystemExit(main())
