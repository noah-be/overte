#!/usr/bin/env python3
"""Host tests for read-only iOS release-readiness aggregation."""

import hashlib
import importlib.util
import json
import plistlib
import struct
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("readiness", ROOT / "ios/tools/check-release-readiness.py")
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def macho_fixture() -> bytes:
    command = struct.pack("<IIIIII", 0x32, 24, 2, 0, 0, 0)
    header = struct.pack(
        "<IiiIIIII", 0xFEEDFACF, 0x0100000C, 0, 2, 1, len(command), 0, 0
    )
    return header + command + b"fixture"

with tempfile.TemporaryDirectory(prefix="overte-readiness-") as temporary:
    root = Path(temporary)
    name = "0042-OverteIOSClient-Debug-device-unsigned.ipa"
    artifact = root / name
    info = {"CFBundleExecutable": "Overte", "LSRequiresIPhoneOS": True, "UIDeviceFamily": [1, 2],
            "UIRequiredDeviceCapabilities": ["arm64"], "MinimumOSVersion": "17.0"}
    privacy_spec = importlib.util.spec_from_file_location("privacy", ROOT / "ios/tools/verify-privacy-manifest.py")
    privacy = importlib.util.module_from_spec(privacy_spec); privacy_spec.loader.exec_module(privacy)
    with zipfile.ZipFile(artifact, "w") as bundle:
        bundle.writestr("Payload/Overte.app/Info.plist", plistlib.dumps(info))
        bundle.writestr("Payload/Overte.app/PrivacyInfo.xcprivacy", plistlib.dumps(privacy.EXPECTED_PRIVACY_MANIFEST))
        bundle.writestr("Payload/Overte.app/Overte", macho_fixture())
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    manifest_name = name[:-4] + ".json"
    manifest = {"buildNumber": 42, "artifact": name, "manifest": manifest_name, "sha256": digest,
                "sourceRevision": "a" * 40, "platform": "iphoneos", "signed": False,
                "requiresSigning": True, "windowsVm": {"sharedFolderRelativePath": name}}
    (root / manifest_name).write_text(json.dumps(manifest))
    (root / "LATEST-OverteIOSClient.json").write_text(json.dumps(manifest))
    (root / "LATEST-OverteIOSClient.txt").write_text(name + "\n")
    build = module.check(root, None)
    assert build["buildReady"] is True and build["deviceAccepted"] is False

    evidence = root / "evidence"
    evidence.mkdir()
    canonical = b"six canonical gate records\n"
    (evidence / "entity-gates.log").write_bytes(canonical)
    (evidence / "entity-gates.json").write_text(json.dumps({"accepted": True, "completed_gates": list(range(6))}))
    handoff = {"containsRawDeviceLog": False, "gateCount": 6, "canonicalGateLogSha256": hashlib.sha256(canonical).hexdigest(),
               "sourceRevision": "a" * 40, "bundleSha256": digest, "formFactor": "ipad"}
    (evidence / "handoff.json").write_text(json.dumps(handoff))
    accepted = module.check(root, evidence)
    assert accepted["status"] == "device-accepted"
    handoff["bundleSha256"] = "0" * 64
    (evidence / "handoff.json").write_text(json.dumps(handoff))
    try:
        module.check(root, evidence)
    except ValueError as error:
        assert "bundle SHA-256" in str(error)
    else:
        raise AssertionError("mismatched device evidence was accepted")

print("PASS iOS release-readiness aggregator tests")
