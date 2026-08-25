#!/usr/bin/env python3
"""Fail closed on the opt-in iOS physical-device E2E Info.plist contract."""

# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import argparse
import plistlib
import sys
from pathlib import Path


CONTRACT_VERSION_KEY = "OverteE2ETestBuildContractVersion"
FILE_SHARING_KEY = "UIFileSharingEnabled"


def validate(info: object, expected: str) -> None:
    if not isinstance(info, dict):
        raise ValueError("Info.plist root is not a dictionary")
    version = info.get(CONTRACT_VERSION_KEY)
    sharing = info.get(FILE_SHARING_KEY)
    if expected == "enabled":
        if version != 1 or isinstance(version, bool):
            raise ValueError("E2E test-build contract version must be integer 1")
        if sharing is not True:
            raise ValueError("E2E test builds must enable Files app result export")
    elif CONTRACT_VERSION_KEY in info or FILE_SHARING_KEY in info:
        raise ValueError("normal iOS builds must not contain E2E test-build markers")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("info_plist", type=Path)
    parser.add_argument("--expected", choices=("enabled", "disabled"), required=True)
    args = parser.parse_args()
    try:
        with args.info_plist.open("rb") as stream:
            info = plistlib.load(stream)
        validate(info, args.expected)
    except (OSError, ValueError, plistlib.InvalidFileException) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(f"PASS iOS E2E test-build contract is {args.expected}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
