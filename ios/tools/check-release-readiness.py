#!/usr/bin/env python3
"""Read-only aggregation of integrated iOS build and device evidence."""

import argparse
import hashlib
import importlib.util
import json
import plistlib
import sys
import zipfile
from pathlib import Path


def load_tool(filename: str, module_name: str):
    path = Path(__file__).with_name(filename)
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {filename}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_single_plist(bundle: zipfile.ZipFile, suffix: str) -> dict:
    matches = [name for name in bundle.namelist() if name.endswith(suffix)]
    if len(matches) != 1:
        raise ValueError(f"artifact must contain exactly one {suffix}")
    value = plistlib.loads(bundle.read(matches[0]))
    if not isinstance(value, dict):
        raise ValueError(f"{suffix} root is not a dictionary")
    return value


def check(artifact_directory: Path, evidence: Path | None) -> dict:
    handoff_tool = load_tool("verify-windows-handoff.py", "windows_handoff")
    privacy_tool = load_tool("verify-privacy-manifest.py", "privacy_manifest")
    artifact_manifest = handoff_tool.verify_handoff(artifact_directory)
    artifact = artifact_directory / artifact_manifest["artifact"]
    with zipfile.ZipFile(artifact) as bundle:
        info = read_single_plist(bundle, "/Info.plist")
        privacy = read_single_plist(bundle, "/PrivacyInfo.xcprivacy")
    if privacy != privacy_tool.EXPECTED_PRIVACY_MANIFEST:
        raise ValueError("bundled privacy manifest differs from the audited allowlist")
    if info.get("LSRequiresIPhoneOS") is not True:
        raise ValueError("artifact is not an iOS application")
    if set(info.get("UIDeviceFamily", [])) != {1, 2}:
        raise ValueError("artifact must target iPhone and iPad")
    if info.get("UIRequiredDeviceCapabilities") != ["arm64"]:
        raise ValueError("artifact must require only arm64")
    if not str(info.get("MinimumOSVersion", "")):
        raise ValueError("artifact has no minimum iOS version")

    device_accepted = False
    evidence_summary = "not provided"
    if evidence is not None:
        evidence_root = evidence
        archive = None
        if evidence.is_file():
            archive = zipfile.ZipFile(evidence)
            names = set(archive.namelist())
            required = {"handoff.json", "entity-gates.json", "entity-gates.log"}
            if names != required:
                raise ValueError("entity evidence ZIP has unexpected or missing entries")
            handoff = json.loads(archive.read("handoff.json"))
            gate_report = json.loads(archive.read("entity-gates.json"))
            canonical = archive.read("entity-gates.log")
        else:
            handoff = json.loads((evidence_root / "handoff.json").read_text())
            gate_report = json.loads((evidence_root / "entity-gates.json").read_text())
            canonical = (evidence_root / "entity-gates.log").read_bytes()
        if archive is not None:
            archive.close()
        if handoff.get("containsRawDeviceLog") is not False or handoff.get("gateCount") != 6:
            raise ValueError("entity evidence handoff is not the minimal six-gate contract")
        if hashlib.sha256(canonical).hexdigest() != handoff.get("canonicalGateLogSha256"):
            raise ValueError("canonical entity gate log SHA-256 mismatch")
        if not gate_report.get("accepted") or len(gate_report.get("completed_gates", [])) != 6:
            raise ValueError("entity gate report is not accepted")
        if handoff.get("sourceRevision") != artifact_manifest.get("sourceRevision"):
            raise ValueError("entity evidence source revision differs from artifact")
        if handoff.get("bundleSha256") != artifact_manifest.get("sha256"):
            raise ValueError("entity evidence bundle SHA-256 differs from artifact")
        if handoff.get("formFactor") != "ipad":
            raise ValueError("entity evidence is not from an iPad")
        device_accepted = True
        evidence_summary = "six entity gates accepted on iPad"

    return {
        "schemaVersion": 1,
        "artifact": artifact.name,
        "buildNumber": artifact_manifest["buildNumber"],
        "buildReady": True,
        "deviceAccepted": device_accepted,
        "status": "device-accepted" if device_accepted else "build-ready",
        "deviceEvidence": evidence_summary,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("artifact_directory", type=Path)
    parser.add_argument("--entity-evidence", type=Path)
    args = parser.parse_args()
    try:
        report = check(args.artifact_directory, args.entity_evidence)
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError, plistlib.InvalidFileException, zipfile.BadZipFile) as error:
        print(json.dumps({"buildReady": False, "deviceAccepted": False, "status": "blocked", "error": str(error)}, indent=2))
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
