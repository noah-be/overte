#!/usr/bin/env python3
"""Verify that a Sideloadly handoff is the exact unsigned Full Client IPA."""

# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path


def load_base_verifier():
    path = Path(__file__).with_name("verify-windows-handoff.py")
    spec = importlib.util.spec_from_file_location("overte_windows_handoff", path)
    if spec is None or spec.loader is None:
        raise ValueError("base handoff verifier is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verify(directory: Path) -> dict:
    payload = load_base_verifier().verify_handoff(directory)
    if payload.get("schemaVersion") != 1:
        raise ValueError("unsupported Full Client manifest schema")
    if payload.get("product") != "overte-ios-integrated-client":
        raise ValueError("handoff is not the integrated Overte Full Client")
    if payload.get("platform") != "iphoneos" or payload.get("architecture") != "arm64":
        raise ValueError("handoff is not an arm64 physical-device IPA")
    if payload.get("signed") is not False or payload.get("requiresSigning") is not True:
        raise ValueError("Sideloadly input must be unsigned and require signing")
    if re.fullmatch(r"[0-9a-f]{40}", str(payload.get("sourceRevision", ""))) is None:
        raise ValueError("Full Client source revision is invalid")
    signing = payload.get("signing")
    if not isinstance(signing, dict):
        raise ValueError("Full Client signing audit is missing")
    if signing != {
        "embeddedProvisioningProfile": False,
        "applicationIdentifier": None,
        "getTaskAllow": None,
    }:
        raise ValueError("unsigned Full Client contains contradictory signing metadata")
    forbidden = {"device", "deviceId", "udid", "serialNumber", "model", "user", "appleId"}
    if forbidden.intersection(payload):
        raise ValueError("handoff manifest contains forbidden private device metadata")
    return payload


def main() -> int:
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} ARTIFACT_DIRECTORY", file=sys.stderr)
        return 2
    try:
        payload = verify(Path(sys.argv[1]))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(
        "Verified unsigned integrated Full Client IPA for Sideloadly: "
        f"{payload['artifact']} ({payload['sha256']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
