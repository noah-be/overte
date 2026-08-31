#!/usr/bin/env python3
"""Validate the security and platform contract of an expanded iOS app bundle."""

# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import plistlib
import re
import sys
from pathlib import Path


EXPECTED_PRIVACY_REASONS = {
    "NSPrivacyAccessedAPICategoryFileTimestamp": ["C617.1"],
    "NSPrivacyAccessedAPICategorySystemBootTime": ["35F9.1"],
    "NSPrivacyAccessedAPICategoryDiskSpace": ["E174.1"],
    "NSPrivacyAccessedAPICategoryUserDefaults": ["CA92.1"],
}
PLATFORM_NAMES = {
    "iphonesimulator": "iPhoneSimulator",
    "iphoneos": "iPhoneOS",
}
FORBIDDEN_NATIVE_SUFFIXES = {".dll", ".dylib", ".so"}
BUNDLE_ID_PATTERN = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9-]*(?:\.[A-Za-z0-9][A-Za-z0-9-]*)+"
)


def numeric_version(value: str) -> tuple[int, ...]:
    if re.fullmatch(r"[0-9]+(?:\.[0-9]+)*", value) is None:
        raise ValueError(f"invalid numeric version: {value}")
    return tuple(map(int, value.split(".")))


def read_plist(path: Path) -> dict:
    if not path.is_file():
        raise ValueError(f"missing bundle metadata: {path.name}")
    with path.open("rb") as stream:
        payload = plistlib.load(stream)
    if not isinstance(payload, dict):
        raise ValueError(f"property list root is not a dictionary: {path.name}")
    return payload


def validate_bundle(app: Path, bundle_id: str, platform: str, minimum_ios: str) -> None:
    if not app.is_dir() or app.suffix != ".app":
        raise ValueError(f"not an expanded app bundle: {app}")
    if BUNDLE_ID_PATTERN.fullmatch(bundle_id) is None:
        raise ValueError(f"invalid expected bundle identifier: {bundle_id}")
    if platform not in PLATFORM_NAMES:
        raise ValueError(f"unsupported Apple platform: {platform}")

    info = read_plist(app / "Info.plist")
    if info.get("CFBundleIdentifier") != bundle_id:
        raise ValueError(f"unexpected bundle identifier: {info.get('CFBundleIdentifier')}")
    if info.get("CFBundlePackageType") != "APPL" or info.get("LSRequiresIPhoneOS") is not True:
        raise ValueError("bundle is not declared as an iOS application")

    executable_name = info.get("CFBundleExecutable")
    if not isinstance(executable_name, str) or Path(executable_name).name != executable_name:
        raise ValueError("bundle executable name is missing or unsafe")
    executable = app / executable_name
    if not executable.is_file() or not executable.stat().st_mode & 0o111:
        raise ValueError(f"bundle executable is missing or not executable: {executable_name}")

    if set(info.get("UIDeviceFamily", [])) != {1, 2}:
        raise ValueError("bundle must target exactly iPhone and iPad")
    if info.get("CFBundleSupportedPlatforms") != [PLATFORM_NAMES[platform]]:
        raise ValueError(f"bundle does not target {platform}")
    if info.get("DTPlatformName") != platform:
        raise ValueError(f"DTPlatformName does not identify {platform}")
    if numeric_version(str(info.get("MinimumOSVersion", ""))) != numeric_version(minimum_ios):
        raise ValueError(f"bundle deployment target is not exactly iOS {minimum_ios}")
    if set(info.get("UIRequiredDeviceCapabilities", [])) != {"arm64"}:
        raise ValueError("bundle must require only the arm64 device capability")

    schemes = {
        scheme
        for entry in info.get("CFBundleURLTypes", [])
        for scheme in entry.get("CFBundleURLSchemes", [])
    }
    if schemes != {"overte", "hifi"}:
        raise ValueError("bundle deep-link schemes differ from the allowlist")

    privacy = read_plist(app / "PrivacyInfo.xcprivacy")
    if privacy.get("NSPrivacyTracking") is not False or privacy.get("NSPrivacyTrackingDomains") != []:
        raise ValueError("bootstrap privacy manifest must declare no tracking")
    reasons = {
        entry.get("NSPrivacyAccessedAPIType"): entry.get("NSPrivacyAccessedAPITypeReasons")
        for entry in privacy.get("NSPrivacyAccessedAPITypes", [])
    }
    if reasons != EXPECTED_PRIVACY_REASONS:
        raise ValueError("privacy required-reason API declarations differ from the audited contract")

    if not (app / "Assets.car").is_file():
        raise ValueError("compiled asset catalog is missing")
    forbidden = sorted(
        str(path.relative_to(app))
        for path in app.rglob("*")
        if path.suffix.lower() in FORBIDDEN_NATIVE_SUFFIXES or path.suffix == ".framework"
    )
    if forbidden:
        raise ValueError(f"bundle contains forbidden native payloads: {', '.join(forbidden)}")


def main() -> int:
    if len(sys.argv) != 5:
        print(
            f"usage: {sys.argv[0]} APP_PATH BUNDLE_ID iphonesimulator|iphoneos MIN_IOS",
            file=sys.stderr,
        )
        return 2
    try:
        validate_bundle(Path(sys.argv[1]), sys.argv[2], sys.argv[3], sys.argv[4])
    except (OSError, ValueError, plistlib.InvalidFileException) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(f"Verified iOS bundle metadata: {sys.argv[1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
