#!/usr/bin/env python3
"""Validate install-critical metadata in an expanded Overte iOS client."""

# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import plistlib
import re
import sys
from pathlib import Path


BUNDLE_ID = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9-]*(?:[.][A-Za-z0-9][A-Za-z0-9-]*)+"
)
APPLE_VERSION = re.compile(r"[0-9]+(?:[.][0-9]+){0,2}")
PLATFORMS = {
    "iphoneos": "iPhoneOS",
    "iphonesimulator": "iPhoneSimulator",
}


def numeric_version(value: str) -> tuple[int, ...]:
    if APPLE_VERSION.fullmatch(value) is None:
        raise ValueError(f"invalid numeric version: {value}")
    return tuple(int(part) for part in value.split("."))


def validate(app: Path, expected_bundle_id: str, platform: str, minimum_ios: str) -> dict:
    if not app.is_dir() or app.suffix != ".app":
        raise ValueError("client path is not an expanded .app bundle")
    if BUNDLE_ID.fullmatch(expected_bundle_id) is None:
        raise ValueError("expected bundle identifier is invalid")
    if platform not in PLATFORMS:
        raise ValueError("platform must be iphoneos or iphonesimulator")
    info_path = app / "Info.plist"
    if not info_path.is_file():
        raise ValueError("client bundle has no Info.plist")
    with info_path.open("rb") as stream:
        info = plistlib.load(stream)
    if not isinstance(info, dict):
        raise ValueError("client Info.plist root is not a dictionary")

    if info.get("CFBundleIdentifier") != expected_bundle_id:
        raise ValueError("client bundle identifier does not match the requested identity")
    if info.get("CFBundlePackageType") != "APPL" or info.get("LSRequiresIPhoneOS") is not True:
        raise ValueError("client bundle is not declared as an iOS application")
    expected_display_name = (
        "Overte E2E" if expected_bundle_id.endswith(".e2e") else "Overte"
    )
    if (info.get("CFBundleDisplayName") != expected_display_name
            or info.get("CFBundleName") != "Overte"):
        raise ValueError("client bundle does not identify the Overte product")
    executable_name = info.get("CFBundleExecutable")
    if executable_name != "Overte":
        raise ValueError("client bundle does not select the Overte executable")
    executable = app / executable_name
    if not executable.is_file() or executable.stat().st_mode & 0o111 == 0:
        raise ValueError("client executable is missing or not executable")

    marketing = str(info.get("CFBundleShortVersionString", ""))
    build = str(info.get("CFBundleVersion", ""))
    if APPLE_VERSION.fullmatch(marketing) is None:
        raise ValueError("client bundle has no valid CFBundleShortVersionString")
    if APPLE_VERSION.fullmatch(build) is None:
        raise ValueError("client bundle has no valid CFBundleVersion")
    if info.get("CFBundleSupportedPlatforms") != [PLATFORMS[platform]]:
        raise ValueError("client bundle targets the wrong Apple platform")
    if info.get("DTPlatformName") != platform:
        raise ValueError("client bundle has inconsistent platform metadata")
    if set(info.get("UIDeviceFamily", [])) != {1, 2}:
        raise ValueError("client bundle must support exactly iPhone and iPad")
    if set(info.get("UIRequiredDeviceCapabilities", [])) != {"arm64"}:
        raise ValueError("client bundle must require arm64")
    if numeric_version(str(info.get("MinimumOSVersion", ""))) != numeric_version(minimum_ios):
        raise ValueError("client minimum iOS version differs from the build contract")
    schemes = {
        scheme
        for entry in info.get("CFBundleURLTypes", [])
        if isinstance(entry, dict)
        for scheme in entry.get("CFBundleURLSchemes", [])
    }
    if schemes != {"hifi", "hifiapp"}:
        raise ValueError("client deep-link schemes differ from the Full Client allowlist")
    return {
        "bundleIdentifier": expected_bundle_id,
        "marketingVersion": marketing,
        "buildVersion": build,
        "platform": platform,
    }


def main() -> int:
    if len(sys.argv) != 5:
        print(
            f"usage: {sys.argv[0]} APP BUNDLE_ID iphoneos|iphonesimulator MIN_IOS",
            file=sys.stderr,
        )
        return 2
    try:
        report = validate(Path(sys.argv[1]), sys.argv[2], sys.argv[3], sys.argv[4])
    except (OSError, ValueError, plistlib.InvalidFileException) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(
        "Verified installable Full Client metadata: "
        f"{report['bundleIdentifier']} "
        f"{report['marketingVersion']} ({report['buildVersion']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
