#!/usr/bin/env python3
"""Verify two inspected build manifests form a real, monotonic upgrade pair."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys


SHA256 = re.compile(r"^[0-9a-f]{64}$")


def manifest(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    required = {
        "apk", "package", "sha256", "signature_verified",
        "signer_certificate_sha256", "version_code", "version_name",
    }
    if not isinstance(value, dict) or not required <= set(value):
        raise ValueError("upgrade artifact manifest is incomplete")
    if (not isinstance(value["apk"], str) or not value["apk"]
            or not isinstance(value["package"], str) or not value["package"]
            or not isinstance(value["version_name"], str) or not value["version_name"]
            or not isinstance(value["version_code"], str)
            or not value["version_code"].isdigit()
            or value["signature_verified"] is not True
            or not isinstance(value["sha256"], str) or not SHA256.fullmatch(value["sha256"])
            or not isinstance(value["signer_certificate_sha256"], str)
            or not SHA256.fullmatch(value["signer_certificate_sha256"])):
        raise ValueError("upgrade artifact manifest fields are invalid")
    return value


def verify(source: dict, candidate: dict) -> dict:
    if source["package"] != candidate["package"]:
        raise ValueError("upgrade artifacts have different package identifiers")
    if source["signer_certificate_sha256"] != candidate["signer_certificate_sha256"]:
        raise ValueError("upgrade artifacts have different signing certificates")
    if source["sha256"] == candidate["sha256"]:
        raise ValueError("upgrade artifacts are byte-identical")
    if source["version_name"] == candidate["version_name"]:
        raise ValueError("upgrade artifacts have the same version name")
    if int(candidate["version_code"]) <= int(source["version_code"]):
        raise ValueError("candidate version code does not increase monotonically")
    return {
        "schemaVersion": 1,
        "package": source["package"],
        "source": {
            "artifact": source["apk"], "sha256": source["sha256"],
            "versionCode": int(source["version_code"]),
            "versionName": source["version_name"],
        },
        "candidate": {
            "artifact": candidate["apk"], "sha256": candidate["sha256"],
            "versionCode": int(candidate["version_code"]),
            "versionName": candidate["version_name"],
        },
        "sameSigner": True,
        "upgradeReady": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-manifest", required=True, type=Path)
    parser.add_argument("--candidate-manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    payload = verify(manifest(args.source_manifest), manifest(args.candidate_manifest))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("Upgrade pair: verified")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(2)
