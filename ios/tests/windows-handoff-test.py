#!/usr/bin/env python3
"""Host tests for the Windows VM artifact handoff verifier."""

# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

import hashlib
import importlib.util
import json
import tempfile
from pathlib import Path


IOS_ROOT = Path(__file__).resolve().parents[1]


def load_verifier():
    path = IOS_ROOT / "tools/verify-windows-handoff.py"
    spec = importlib.util.spec_from_file_location("windows_handoff", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> None:
    verifier = load_verifier()
    with tempfile.TemporaryDirectory(prefix="overte-handoff-") as temporary:
        root = Path(temporary)
        name = "0042-OverteIOSClient-Debug-device-unsigned.ipa"
        artifact = root / name
        artifact.write_bytes(b"deterministic IPA fixture")
        payload = {
            "buildNumber": 42,
            "artifact": name,
            "manifest": "0042-OverteIOSClient-Debug-device-unsigned.json",
            "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
            "platform": "iphoneos",
            "signed": False,
            "requiresSigning": True,
            "windowsVm": {"sharedFolderRelativePath": name},
        }
        latest_json = root / "LATEST-OverteIOSClient.json"
        latest_text = root / "LATEST-OverteIOSClient.txt"
        latest_json.write_text(json.dumps(payload), encoding="utf-8")
        latest_text.write_text(name + "\n", encoding="utf-8")
        (root / payload["manifest"]).write_text(json.dumps(payload), encoding="utf-8")
        assert verifier.verify_handoff(root) == payload

        for mutation, expected in (
            ({"sha256": "0" * 64}, "SHA-256"),
            ({"buildNumber": 41}, "buildNumber"),
            ({"requiresSigning": False}, "signing is required"),
        ):
            broken = payload | mutation
            latest_json.write_text(json.dumps(broken), encoding="utf-8")
            (root / payload["manifest"]).write_text(json.dumps(broken), encoding="utf-8")
            try:
                verifier.verify_handoff(root)
            except ValueError as error:
                assert expected in str(error)
            else:
                raise AssertionError(f"unsafe handoff accepted: {mutation}")

    print("PASS Windows VM handoff verifier tests")


if __name__ == "__main__":
    main()
