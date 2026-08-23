#!/usr/bin/env python3
"""Enforce the Android main -> platform -> target synchronization paths."""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys


PARENTS = {
    "android-phone": "android-main",
    "android-vr": "android-main",
    "android-vr-pico": "android-vr",
    "android-vr-quest": "android-vr",
}
SHARED_PATHS = ("tests/device", "android/common/device_tests")


def git(repository: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repository), *arguments],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def validate(
    repository: Path,
    target: str,
    android_main: str,
    android_vr: str,
    head: str,
) -> list[str]:
    errors = []
    if target not in PARENTS:
        return [f"unsupported Android target branch: {target}"]

    parent_name = PARENTS[target]
    parent = android_main if parent_name == "android-main" else android_vr
    ancestry = git(repository, "merge-base", "--is-ancestor", parent, head)
    if ancestry.returncode != 0:
        errors.append(f"{target} must contain the current {parent_name} history")

    for shared_path in SHARED_PATHS:
        shared_diff = git(
            repository, "diff", "--quiet", android_main, head, "--", shared_path
        )
        if shared_diff.returncode != 0:
            errors.append(
                f"{shared_path} differs from android-main; route shared changes "
                "through android-main"
            )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--target", required=True, choices=sorted(PARENTS))
    parser.add_argument("--android-main", default="origin/android-main")
    parser.add_argument("--android-vr", default="origin/android-vr")
    parser.add_argument("--head", default="HEAD")
    args = parser.parse_args()
    errors = validate(
        args.repository.resolve(),
        args.target,
        args.android_main,
        args.android_vr,
        args.head,
    )
    if errors:
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
        return 1
    print("PASS: Android branch topology preserves the required parent sync path")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
