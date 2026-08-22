#!/usr/bin/env python3
"""Host contracts for strict Full Client Sideloadly handoff verification."""

# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import hashlib
import importlib.util
import json
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def load_verifier():
    path = ROOT / "ios/tools/verify-sideload-handoff.py"
    spec = importlib.util.spec_from_file_location("sideload_handoff", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fixture(root: Path) -> dict:
    name = "0042-OverteIOSClient-Debug-device-unsigned.ipa"
    artifact = root / name
    artifact.write_bytes(b"integrated client fixture")
    payload = {
        "schemaVersion": 1,
        "product": "overte-ios-integrated-client",
        "buildNumber": 42,
        "artifact": name,
        "manifest": name[:-4] + ".json",
        "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
        "sourceRevision": "a" * 40,
        "platform": "iphoneos",
        "architecture": "arm64",
        "configuration": "Debug",
        "xcode": "Xcode 26.6",
        "sdk": "26.5",
        "signed": False,
        "requiresSigning": True,
        "signing": {
            "embeddedProvisioningProfile": False,
            "applicationIdentifier": None,
            "getTaskAllow": None,
        },
        "windowsVm": {"sharedFolderRelativePath": name},
    }
    (root / payload["manifest"]).write_text(json.dumps(payload), encoding="utf-8")
    (root / "LATEST-OverteIOSClient.json").write_text(json.dumps(payload), encoding="utf-8")
    (root / "LATEST-OverteIOSClient.txt").write_text(name + "\n", encoding="utf-8")
    return payload


verifier = load_verifier()
with tempfile.TemporaryDirectory(prefix="overte-sideload-handoff-") as temporary:
    root = Path(temporary)
    payload = fixture(root)
    assert verifier.verify(root) == payload
    for field, value, expected in (
        ("product", "overte-ios-bootstrap", "not the integrated"),
        ("architecture", "x86_64", "arm64"),
        ("model", "private", "private device metadata"),
    ):
        broken = payload | {field: value}
        (root / payload["manifest"]).write_text(json.dumps(broken), encoding="utf-8")
        (root / "LATEST-OverteIOSClient.json").write_text(json.dumps(broken), encoding="utf-8")
        try:
            verifier.verify(root)
        except ValueError as error:
            assert expected in str(error), error
        else:
            raise AssertionError(f"unsafe Sideloadly handoff accepted: {field}")

print("PASS strict Full Client Sideloadly handoff contracts")
