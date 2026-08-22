#!/usr/bin/env python3
"""Bind all iOS simulator world screenshots to one verified client candidate."""

# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys


REVISION = re.compile(r"^[0-9a-f]{40}$")
DIGEST = re.compile(r"^[0-9a-f]{64}$")
SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,255}$")
CASES = (
    ("iphone", "serverless", "serverless_tutorial"),
    ("iphone", "online", "overte_hub"),
    ("ipad", "serverless", "serverless_tutorial"),
    ("ipad", "online", "overte_hub"),
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate(
    evidence_dir: Path,
    candidate_manifest: Path,
    source_revision: str,
    candidate_sha256: str,
) -> dict[str, object]:
    if REVISION.fullmatch(source_revision) is None or DIGEST.fullmatch(candidate_sha256) is None:
        raise ValueError("candidate revision or SHA-256 has an invalid format")
    manifest = json.loads(candidate_manifest.read_text(encoding="utf-8"))
    if (
        manifest.get("schemaVersion") != 1
        or manifest.get("product") != "overte-ios-integrated-client"
        or manifest.get("platform") != "iphonesimulator"
        or manifest.get("architecture") != "arm64"
        or manifest.get("sourceRevision") != source_revision
        or manifest.get("sha256") != candidate_sha256
    ):
        raise ValueError("simulator candidate manifest does not match the approved build")
    artifact_name = str(manifest.get("artifact", ""))
    if SAFE_NAME.fullmatch(artifact_name) is None or not artifact_name.endswith(".zip"):
        raise ValueError("simulator candidate artifact name is unsafe")
    artifact = candidate_manifest.parent / artifact_name
    if not artifact.is_file() or sha256(artifact) != candidate_sha256:
        raise ValueError("simulator candidate payload SHA-256 mismatch")
    if list(evidence_dir.rglob("*.log")):
        raise ValueError("raw runtime logs must not enter retained world evidence")

    cases: list[dict[str, object]] = []
    screenshot_hashes: dict[tuple[str, str], str] = {}
    expected_files: set[str] = set()
    for family, scenario, destination in CASES:
        stem = f"{family}-{scenario}"
        screenshot_path = evidence_dir / f"{stem}.png"
        screenshot_report_path = evidence_dir / f"{stem}-screenshot.json"
        runtime_path = evidence_dir / f"{stem}-runtime.json"
        expected_files.update(path.name for path in (screenshot_path, screenshot_report_path, runtime_path))
        if not all(path.is_file() for path in (screenshot_path, screenshot_report_path, runtime_path)):
            raise ValueError(f"world evidence case is incomplete: {stem}")
        screenshot = json.loads(screenshot_report_path.read_text(encoding="utf-8"))
        runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
        actual_sha = sha256(screenshot_path)
        if (
            screenshot.get("accepted") is not True
            or screenshot.get("scenario") != scenario
            or screenshot.get("destination") != destination
            or screenshot.get("file") != screenshot_path.name
            or screenshot.get("sha256") != actual_sha
        ):
            raise ValueError(f"retained screenshot report is inconsistent: {stem}")
        if (
            runtime.get("accepted") is not True
            or runtime.get("scenario") != scenario
            or runtime.get("destination") != destination
            or runtime.get("containsRawRuntimeLog") is not False
            or runtime.get("screenshot", {}).get("sha256") != actual_sha
        ):
            raise ValueError(f"runtime/screenshot binding is inconsistent: {stem}")
        if scenario == "online" and not runtime.get("resolvedDomainId"):
            raise ValueError(f"online evidence has no resolved domain binding: {stem}")
        if scenario == "serverless" and runtime.get("resolvedDomainId") is not None:
            raise ValueError(f"serverless evidence unexpectedly names a domain: {stem}")
        screenshot_hashes[(family, scenario)] = actual_sha
        cases.append(
            {
                "family": family,
                "scenario": scenario,
                "destination": destination,
                "screenshot": screenshot_path.name,
                "screenshotSha256": actual_sha,
                "runtime": runtime_path.name,
            }
        )

    retained = {path.name for path in evidence_dir.iterdir() if path.is_file()}
    if retained != expected_files:
        raise ValueError("world evidence directory contains unexpected or missing files")
    for family in ("iphone", "ipad"):
        if screenshot_hashes[(family, "serverless")] == screenshot_hashes[(family, "online")]:
            raise ValueError(f"{family} serverless and online screenshots are byte-identical")
    return {
        "schemaVersion": 1,
        "accepted": True,
        "sourceRevision": source_revision,
        "candidateArtifact": artifact_name,
        "candidateSha256": candidate_sha256,
        "platform": "iphonesimulator",
        "architecture": "arm64",
        "worldsVisuallyDistinct": True,
        "cases": cases,
        "containsRawRuntimeLogs": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence_dir", type=Path)
    parser.add_argument("--candidate-manifest", type=Path, required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--candidate-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = validate(
            args.evidence_dir,
            args.candidate_manifest,
            args.source_revision,
            args.candidate_sha256,
        )
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
