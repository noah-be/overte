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
}
SHARED_PATHS = ("tests/device", "android/common/device_tests")
TARGET_SHARED_PATH_EXCLUSIONS = {
    "android-phone": {
        "tests/device": (
            "tests/device/adapters/appium/README.md",
            "tests/device/adapters/appium/adapter.py",
            "tests/device/jenkins/Jenkinsfile",
            "tests/device/jenkins/README.md",
            "tests/device/jenkins/run_ci.py",
            "tests/device/jenkins/test_run_ci.py",
            "tests/device/policies/android-phone-flat-touch.json",
            "tests/device/self_tests/test_appium_adapter.py",
        ),
    },
    "android-vr-pico": {
        "tests/device": (
            "tests/device/jenkins/test_conan_cache_manager.py",
            "tests/device/jenkins/test_local_lab.py",
            "tests/device/self_tests/test_pico_openxr_adapter_session.py",
        ),
    },
}


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
        pathspecs = [shared_path]
        pathspecs.extend(
            f":(exclude){path}"
            for path in TARGET_SHARED_PATH_EXCLUSIONS.get(target, {}).get(
                shared_path, ()
            )
        )
        shared_diff = git(
            repository, "diff", "--quiet", android_main, head, "--", *pathspecs
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
