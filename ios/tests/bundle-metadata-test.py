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
        "CFBundleIdentifier": "org.overte.bootstrap.dev",
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

        validator.validate_bundle(app, "org.overte.bootstrap.dev", "iphonesimulator", "17.0")

        framework = app / "Frameworks/Desktop.framework"
        framework.mkdir(parents=True)
        try:
            validator.validate_bundle(app, "org.overte.bootstrap.dev", "iphonesimulator", "17.0")
        except ValueError as error:
            assert "forbidden native payloads" in str(error)
        else:
            raise AssertionError("embedded framework was accepted")
        framework.rmdir()
        framework.parent.rmdir()

        metadata_cases = (
            ("MinimumOSVersion", "18.0", "deployment target"),
            ("CFBundleExecutable", "../unsafe", "unsafe"),
            ("UIDeviceFamily", [1], "iPhone and iPad"),
            ("DTPlatformName", "iphoneos", "DTPlatformName"),
        )
        for key, value, expected in metadata_cases:
            write_info(app / "Info.plist")
            with (app / "Info.plist").open("rb") as stream:
                payload = plistlib.load(stream)
            payload[key] = value
            with (app / "Info.plist").open("wb") as stream:
                plistlib.dump(payload, stream)
            try:
                validator.validate_bundle(app, "org.overte.bootstrap.dev", "iphonesimulator", "17.0")
            except ValueError as error:
                assert expected in str(error)
            else:
                raise AssertionError(f"unsafe metadata was accepted: {key}")

        write_info(app / "Info.plist")
        (app / "Assets.car").unlink()
        try:
            validator.validate_bundle(app, "org.overte.bootstrap.dev", "iphonesimulator", "17.0")
        except ValueError as error:
            assert "asset catalog" in str(error)
        else:
            raise AssertionError("bundle without compiled assets was accepted")
        (app / "Assets.car").write_bytes(b"compiled-assets-fixture")

        forbidden_dylib = app / "libInjected.dylib"
        forbidden_dylib.touch()
        try:
            validator.validate_bundle(app, "org.overte.bootstrap.dev", "iphonesimulator", "17.0")
        except ValueError as error:
            assert "forbidden native payloads" in str(error)
        else:
            raise AssertionError("dynamic library payload was accepted")
        forbidden_dylib.unlink()

        privacy_path = app / "PrivacyInfo.xcprivacy"
        with privacy_path.open("rb") as stream:
            privacy = plistlib.load(stream)
        privacy["NSPrivacyTracking"] = True
        with privacy_path.open("wb") as stream:
            plistlib.dump(privacy, stream)
        try:
            validator.validate_bundle(app, "org.overte.bootstrap.dev", "iphonesimulator", "17.0")
        except ValueError as error:
            assert "no tracking" in str(error)
        else:
            raise AssertionError("tracking-enabled privacy manifest was accepted")

    print("PASS iOS bundle metadata tests")


if __name__ == "__main__":
    main()
