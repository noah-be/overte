#!/usr/bin/env python3
"""Host tests for install-critical Full Client bundle metadata."""

# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import importlib.util
import plistlib
import tempfile
from pathlib import Path


IOS_ROOT = Path(__file__).resolve().parents[1]


def load_validator():
    path = IOS_ROOT / "tools/verify-client-bundle-info.py"
    specification = importlib.util.spec_from_file_location("client_bundle_info", path)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def valid_info() -> dict:
    return {
        "CFBundleIdentifier": "org.overte.interface.dev",
        "CFBundleExecutable": "Overte",
        "CFBundleDisplayName": "Overte",
        "CFBundleName": "Overte",
        "CFBundlePackageType": "APPL",
        "CFBundleShortVersionString": "0.1.0",
        "CFBundleVersion": "1",
        "CFBundleSupportedPlatforms": ["iPhoneOS"],
        "DTPlatformName": "iphoneos",
        "LSRequiresIPhoneOS": True,
        "MinimumOSVersion": "17.0",
        "UIDeviceFamily": [1, 2],
        "UIRequiredDeviceCapabilities": ["arm64"],
        "CFBundleURLTypes": [{"CFBundleURLSchemes": ["hifi", "hifiapp"]}],
    }


def expect_failure(validator, app: Path, expected: str) -> None:
    try:
        validator.validate(app, "org.overte.interface.dev", "iphoneos", "17.0")
    except ValueError as error:
        assert expected in str(error), (expected, str(error))
    else:
        raise AssertionError(f"invalid client bundle accepted; expected {expected}")


def main() -> None:
    validator = load_validator()
    with tempfile.TemporaryDirectory(prefix="overte-client-bundle-") as temporary:
        app = Path(temporary) / "Overte.app"
        app.mkdir()
        executable = app / "Overte"
        executable.write_bytes(b"Mach-O fixture")
        executable.chmod(0o755)
        info_path = app / "Info.plist"

        payload = valid_info()
        with info_path.open("wb") as stream:
            plistlib.dump(payload, stream)
        assert validator.validate(app, "org.overte.interface.dev", "iphoneos", "17.0") == {
            "bundleIdentifier": "org.overte.interface.dev",
            "marketingVersion": "0.1.0",
            "buildVersion": "1",
            "platform": "iphoneos",
        }

        cases = (
            ("CFBundleIdentifier", None, "bundle identifier"),
            ("CFBundleShortVersionString", None, "CFBundleShortVersionString"),
            ("CFBundleVersion", None, "CFBundleVersion"),
            ("CFBundleShortVersionString", "Dev-2026", "CFBundleShortVersionString"),
            ("CFBundleVersion", "", "CFBundleVersion"),
            ("CFBundleSupportedPlatforms", ["iPhoneSimulator"], "wrong Apple platform"),
            ("DTPlatformName", "iphonesimulator", "inconsistent platform"),
            ("CFBundleURLTypes", [{"CFBundleURLSchemes": ["overte"]}], "deep-link schemes"),
        )
        for key, value, expected in cases:
            payload = valid_info()
            if value is None:
                payload.pop(key)
            else:
                payload[key] = value
            with info_path.open("wb") as stream:
                plistlib.dump(payload, stream)
            expect_failure(validator, app, expected)

    print("PASS install-critical Full Client bundle metadata tests")


if __name__ == "__main__":
    main()
