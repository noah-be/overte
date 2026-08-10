#!/usr/bin/env python3
"""Validate Overte's audited iOS privacy-manifest contract."""

# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import plistlib
import sys
from pathlib import Path


EXPECTED_PRIVACY_MANIFEST = {
    "NSPrivacyAccessedAPITypes": [
        {"NSPrivacyAccessedAPIType": "NSPrivacyAccessedAPICategoryFileTimestamp", "NSPrivacyAccessedAPITypeReasons": ["C617.1"]},
        {"NSPrivacyAccessedAPIType": "NSPrivacyAccessedAPICategorySystemBootTime", "NSPrivacyAccessedAPITypeReasons": ["35F9.1"]},
        {"NSPrivacyAccessedAPIType": "NSPrivacyAccessedAPICategoryDiskSpace", "NSPrivacyAccessedAPITypeReasons": ["E174.1"]},
        {"NSPrivacyAccessedAPIType": "NSPrivacyAccessedAPICategoryUserDefaults", "NSPrivacyAccessedAPITypeReasons": ["CA92.1"]},
    ],
    "NSPrivacyCollectedDataTypes": [],
    "NSPrivacyTracking": False,
    "NSPrivacyTrackingDomains": [],
}


def validate_privacy_manifest(path: Path) -> None:
    if not path.is_file() or path.name != "PrivacyInfo.xcprivacy":
        raise ValueError("privacy manifest is missing or has the wrong bundle name")
    with path.open("rb") as stream:
        payload = plistlib.load(stream)
    if payload != EXPECTED_PRIVACY_MANIFEST:
        raise ValueError("privacy manifest differs from the audited required-reason allowlist")


def main() -> int:
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} PrivacyInfo.xcprivacy", file=sys.stderr)
        return 2
    try:
        validate_privacy_manifest(Path(sys.argv[1]))
    except (OSError, ValueError, plistlib.InvalidFileException) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(f"Verified iOS privacy manifest: {sys.argv[1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
