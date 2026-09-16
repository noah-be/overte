#!/usr/bin/env python3
"""Validate the exported Info.plist of an explicitly isolated iOS E2E build."""

from __future__ import annotations

import argparse
from pathlib import Path
import plistlib
import sys


CONTRACT_KEY = "OverteE2ETestBuildContractVersion"


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plist", type=Path, required=True,
                        help="exported app Info.plist (XML or binary)")
    parser.add_argument("--bundle-id", help="expected dedicated E2E bundle identifier")
    return parser.parse_args()


def validate(path: Path, expected_bundle_id: str | None) -> dict:
    with path.open("rb") as source:
        value = plistlib.load(source)
    if not isinstance(value, dict):
        raise ValueError("Info.plist root must be a dictionary")
    version = value.get(CONTRACT_KEY)
    if isinstance(version, bool) or version != 1:
        raise ValueError(f"{CONTRACT_KEY} must be integer 1")
    if value.get("UIFileSharingEnabled") is not True:
        raise ValueError("UIFileSharingEnabled must be true for real-device Documents transfer")
    if expected_bundle_id is not None:
        if not expected_bundle_id or value.get("CFBundleIdentifier") != expected_bundle_id:
            raise ValueError("CFBundleIdentifier does not match the dedicated E2E bundle ID")
    return value


def main() -> int:
    args = arguments()
    value = validate(args.plist.resolve(), args.bundle_id)
    bundle = value.get("CFBundleIdentifier", "fragment")
    print(f"PASS: {bundle} declares iOS E2E test-build contract version 1")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, plistlib.InvalidFileException) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(2)
