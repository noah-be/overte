#!/usr/bin/env python3
"""Verify a signed iPad bundle, profile and entitlements without exposing identity data."""

# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import argparse
import datetime as dt
import os
import plistlib
import re
import stat
import subprocess
import sys
from pathlib import Path


BUNDLE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]*(?:[.][A-Za-z0-9][A-Za-z0-9-]*)+")
APPLICATION_ID = re.compile(r"[A-Z0-9]{4,32}[.][A-Za-z0-9.-]+")


def require_device_identifier() -> str:
    path_text = os.environ.get("OVERTE_IOS_IPAD_DEVICE_ID_FILE", "")
    if not path_text:
        raise ValueError("OVERTE_IOS_IPAD_DEVICE_ID_FILE is required")
    path = Path(path_text)
    metadata = path.lstat()
    if not stat.S_ISREG(metadata.st_mode) or path.is_symlink():
        raise ValueError("the iPad identity file must be a regular file")
    if stat.S_IMODE(metadata.st_mode) != 0o600:
        raise ValueError("the iPad identity file must have mode 0600")
    lines = path.read_text(encoding="utf-8").splitlines()
    if len(lines) != 1 or not re.fullmatch(r"[A-Za-z0-9.-]{8,128}", lines[0]):
        raise ValueError("the iPad identity file is invalid")
    return lines[0]


def validate_metadata(
    profile: dict,
    signature: dict,
    info: dict,
    expected_bundle_id: str,
    expected_application_id: str,
    device_identifier: str,
    now: dt.datetime | None = None,
) -> None:
    if BUNDLE_ID.fullmatch(expected_bundle_id) is None:
        raise ValueError("expected bundle identifier is invalid")
    if APPLICATION_ID.fullmatch(expected_application_id) is None:
        raise ValueError("expected application identifier is invalid")
    if info.get("CFBundleIdentifier") != expected_bundle_id:
        raise ValueError("bundle identifier differs from the verified candidate")

    profile_entitlements = profile.get("Entitlements")
    teams = profile.get("TeamIdentifier")
    if not isinstance(profile_entitlements, dict) or not isinstance(teams, list) or len(teams) != 1:
        raise ValueError("provisioning profile has invalid team metadata")
    team = teams[0]
    expected = f"{team}.{expected_bundle_id}"
    if expected != expected_application_id:
        raise ValueError("manifest application identifier differs from profile team and bundle")
    if signature.get("application-identifier") != expected:
        raise ValueError("signature application identifier mismatch")
    if profile_entitlements.get("application-identifier") != expected:
        raise ValueError("profile application identifier mismatch")
    if signature.get("com.apple.developer.team-identifier") != team:
        raise ValueError("signature team identifier mismatch")

    signature_debug = signature.get("get-task-allow", False)
    profile_debug = profile_entitlements.get("get-task-allow", False)
    if not isinstance(signature_debug, bool) or signature_debug != profile_debug:
        raise ValueError("get-task-allow differs between signature and profile")

    expiration = profile.get("ExpirationDate")
    if not isinstance(expiration, dt.datetime):
        raise ValueError("provisioning profile has no expiration date")
    if expiration.tzinfo is None:
        expiration = expiration.replace(tzinfo=dt.timezone.utc)
    current = now or dt.datetime.now(dt.timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=dt.timezone.utc)
    if expiration <= current:
        raise ValueError("provisioning profile is expired")

    provisioned = profile.get("ProvisionedDevices")
    all_devices = profile.get("ProvisionsAllDevices") is True
    if not all_devices and (
        not isinstance(provisioned, list) or device_identifier not in provisioned
    ):
        raise ValueError("provisioning profile does not authorize the fixed iPad")


def run(command: list[str], description: str) -> bytes:
    completed = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if completed.returncode != 0:
        raise ValueError(f"{description} failed")
    return completed.stdout


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("app", type=Path)
    parser.add_argument("--expected-bundle-id", required=True)
    parser.add_argument("--expected-application-identifier", required=True)
    args = parser.parse_args()
    try:
        if args.app.is_symlink() or not args.app.is_dir() or args.app.suffix != ".app":
            raise ValueError("application path is invalid")
        app = args.app.resolve(strict=True)
        device_identifier = require_device_identifier()
        run(["codesign", "--verify", "--deep", "--strict", str(app)], "code signature verification")
        profile = plistlib.loads(
            run(["security", "cms", "-D", "-i", str(app / "embedded.mobileprovision")], "profile decoding")
        )
        signature = plistlib.loads(
            run(["codesign", "-d", "--entitlements", ":-", str(app)], "entitlement extraction")
        )
        with (app / "Info.plist").open("rb") as stream:
            info = plistlib.load(stream)
        if not all(isinstance(value, dict) for value in (profile, signature, info)):
            raise ValueError("signing metadata root is invalid")
        validate_metadata(
            profile,
            signature,
            info,
            args.expected_bundle_id,
            args.expected_application_identifier,
            device_identifier,
        )
    except (OSError, ValueError, plistlib.InvalidFileException) as error:
        print(f"error: signed iPad candidate rejected: {error}", file=sys.stderr)
        return 1
    print("PASS signed iPad candidate provenance")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
