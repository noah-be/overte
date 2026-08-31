#!/usr/bin/env python3
"""Verify an offline integrated-client handoff before copying it to Windows."""

# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path


ARTIFACT_PATTERN = re.compile(
    r"(?P<number>[0-9]{4,})-OverteIOSClient-(?P<configuration>[^-]+)-"
    r"(?P<target>device-(?:unsigned|signed)|simulator)\.(?P<extension>ipa|zip)"
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_handoff(directory: Path) -> dict:
    latest_json = directory / "LATEST-OverteIOSClient.json"
    latest_text = directory / "LATEST-OverteIOSClient.txt"
    if not latest_json.is_file() or not latest_text.is_file():
        raise ValueError("LATEST JSON and text pointers are both required")
    payload = json.loads(latest_json.read_text(encoding="utf-8"))
    artifact_name = latest_text.read_text(encoding="utf-8").strip()
    if not artifact_name or Path(artifact_name).name != artifact_name:
        raise ValueError("LATEST text contains an unsafe artifact name")
    if payload.get("artifact") != artifact_name:
        raise ValueError("LATEST text and JSON select different artifacts")
    match = ARTIFACT_PATTERN.fullmatch(artifact_name)
    if match is None:
        raise ValueError("artifact filename is not a numbered integrated-client artifact")
    if int(match.group("number")) != payload.get("buildNumber"):
        raise ValueError("artifact filename number does not match buildNumber")
    expected_manifest_name = str(Path(artifact_name).with_suffix(".json"))
    if payload.get("manifest") != expected_manifest_name:
        raise ValueError("manifest name does not match the numbered artifact")
    numbered_manifest = directory / expected_manifest_name
    if not numbered_manifest.is_file():
        raise ValueError("numbered artifact manifest is missing")
    if json.loads(numbered_manifest.read_text(encoding="utf-8")) != payload:
        raise ValueError("LATEST JSON and numbered artifact manifest differ")
    artifact = directory / artifact_name
    if not artifact.is_file():
        raise ValueError("selected artifact is missing")
    digest = sha256_file(artifact)
    if digest != payload.get("sha256"):
        raise ValueError("artifact SHA-256 does not match the manifest")
    if payload.get("windowsVm", {}).get("sharedFolderRelativePath") != artifact_name:
        raise ValueError("Windows shared-folder path does not select the current artifact")
    signed = payload.get("signed")
    requires_signing = payload.get("requiresSigning")
    if match.group("target") == "device-unsigned":
        if signed is not False or requires_signing is not True:
            raise ValueError("unsigned device artifact must disclose that signing is required")
    elif match.group("target") == "device-signed":
        if signed is not True or requires_signing is not False:
            raise ValueError("signed device artifact has inconsistent signing metadata")
    elif signed is not False or requires_signing is not False:
        raise ValueError("simulator artifact signing metadata is inconsistent")
    return payload


def main() -> int:
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} ARTIFACT_DIRECTORY", file=sys.stderr)
        return 2
    try:
        payload = verify_handoff(Path(sys.argv[1]))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    if payload["requiresSigning"]:
        guidance = "unsigned device IPA verified; Sideloadly must sign it before installation"
    elif payload["platform"] == "iphoneos":
        guidance = "pre-signed device IPA verified; use only on a device allowed by its profile"
    else:
        guidance = "simulator artifact verified; it cannot be installed on an iPad"
    print(f"Verified current artifact {payload['artifact']}: {guidance}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
