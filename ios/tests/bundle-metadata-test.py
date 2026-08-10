#!/usr/bin/env python3
"""Host tests for expanded iOS bundle metadata verification."""

# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import importlib.util
import plistlib
import shutil
import tempfile
from pathlib import Path


IOS_ROOT = Path(__file__).resolve().parents[1]


def load_validator():
    path = IOS_ROOT / "tools/verify-bundle-metadata.py"
    specification = importlib.util.spec_from_file_location("verify_bundle_metadata", path)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def write_info(path: Path) -> None:
    payload = {
        "CFBundleExecutable": "OverteIOSBootstrap",
        "CFBundleIdentifier": "org.overte.interface.dev",
        "CFBundlePackageType": "APPL",
        "CFBundleSupportedPlatforms": ["iPhoneSimulator"],
        "CFBundleURLTypes": [
            {"CFBundleURLSchemes": ["overte", "hifi"]},
        ],
        "DTPlatformName": "iphonesimulator",
        "LSRequiresIPhoneOS": True,
        "MinimumOSVersion": "17.0",
        "UIDeviceFamily": [1, 2],
        "UIRequiredDeviceCapabilities": ["arm64"],
    }
    with path.open("wb") as stream:
        plistlib.dump(payload, stream)


def main() -> None:
    validator = load_validator()
    with tempfile.TemporaryDirectory(prefix="overte-ios-bundle-") as temporary:
        app = Path(temporary) / "OverteIOSBootstrap.app"
        app.mkdir()
        write_info(app / "Info.plist")
        shutil.copy2(IOS_ROOT / "resources/PrivacyInfo.xcprivacy", app)
        (app / "Assets.car").write_bytes(b"compiled-assets-fixture")
        executable = app / "OverteIOSBootstrap"
        executable.write_bytes(b"Mach-O fixture")
        executable.chmod(executable.stat().st_mode | 0o100)

        validator.validate_bundle(app, "org.overte.interface.dev", "iphonesimulator", "17.0")

        framework = app / "Frameworks/Desktop.framework"
        framework.mkdir(parents=True)
        try:
            validator.validate_bundle(app, "org.overte.interface.dev", "iphonesimulator", "17.0")
        except ValueError as error:
            assert "forbidden native payloads" in str(error)
        else:
            raise AssertionError("embedded framework was accepted")
        framework.rmdir()
        framework.parent.rmdir()

        with (app / "Info.plist").open("rb") as stream:
            wrong_target = plistlib.load(stream)
        wrong_target["MinimumOSVersion"] = "18.0"
        with (app / "Info.plist").open("wb") as stream:
            plistlib.dump(wrong_target, stream)
        try:
            validator.validate_bundle(app, "org.overte.interface.dev", "iphonesimulator", "17.0")
        except ValueError as error:
            assert "deployment target" in str(error)
        else:
            raise AssertionError("unexpected deployment target was accepted")

    print("PASS iOS bundle metadata tests")


if __name__ == "__main__":
    main()
