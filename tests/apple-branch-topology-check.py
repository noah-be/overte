#!/usr/bin/env python3
"""Enforce that shared Apple device harness changes flow through apple-main."""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys


def git(repository: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", str(repository), *arguments], text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)


def validate(repository: Path, apple_main: str, head: str) -> list[str]:
    errors = []
    ancestry = git(repository, "merge-base", "--is-ancestor", apple_main, head)
    if ancestry.returncode != 0:
        errors.append("apple-ios and apple-macos must contain the current apple-main history")
    shared_diff = git(repository, "diff", "--quiet", apple_main, head, "--", "tests/device")
    if shared_diff.returncode != 0:
        errors.append("tests/device differs from apple-main; route shared harness changes through apple-main")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--apple-main", default="origin/apple-main")
    parser.add_argument("--head", default="HEAD")
    args = parser.parse_args()
    errors = validate(args.repository.resolve(), args.apple_main, args.head)
    if errors:
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
        return 1
    print("PASS: Apple branch topology preserves main -> apple-main -> target flow")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
