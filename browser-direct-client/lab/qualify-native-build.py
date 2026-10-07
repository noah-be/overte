#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Bind a completed own native build/test run to unchanged source and runtime bytes."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

from manage import REPO, ROOT

spec = importlib.util.spec_from_file_location("own_native_snapshot", Path(__file__).with_name("snapshot-runtime.py"))
snapshot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(snapshot)

EXPECTED_TESTS = {
    "browser-direct-transport-BrowserEntityProjectionTests-test",
    "browser-direct-transport-NativeAvatarAudioWireTests-test",
    "browser-direct-transport-WebRTCTransportTests-test",
    "networking-PacketTests-test", "networking-ReceivedMessageTests-test",
    "networking-SequenceNumberStatsTests-test",
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def native_test_evidence(test_log: Path, junit: Path) -> dict:
    text = test_log.read_text()
    totals = [{"passed": int(passed), "failed": int(failed), "skipped": int(skipped)}
              for passed, failed, skipped in re.findall(
                  r"Totals:\s+(\d+) passed, (\d+) failed, (\d+) skipped", text)]
    cases = ET.parse(junit).getroot().findall(".//testcase")
    if len(totals) != 6 or len(cases) != 6 or {case.get("name") for case in cases} != EXPECTED_TESTS or \
            any(not item["passed"] or item["failed"] or item["skipped"] for item in totals) or \
            any(any(case.find(tag) is not None for tag in ("failure", "error", "skipped")) for case in cases) or \
            "100% tests passed, 0 tests failed out of 6" not in text:
        raise RuntimeError("All six ordinary native test programs must pass without failures or skips")
    return {"passed": 6, "failed": 0, "skipped": 0, "testNames": sorted(EXPECTED_TESTS),
            "qtTotals": totals, "ctestTimeoutSeconds": 45,
            "logSHA256": digest(test_log), "junitSHA256": digest(junit)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-before", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--build-log", type=Path, required=True)
    parser.add_argument("--build-exit-code", type=int, choices=(0,), required=True)
    parser.add_argument("--test-log", type=Path, required=True)
    parser.add_argument("--junit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    for path in (args.source_before, args.candidate, args.build_log, args.test_log, args.junit):
        if not path.resolve().is_relative_to((REPO / "build/browser-direct").resolve()) or not path.is_file():
            parser.error("Inputs must be existing evidence from this worktree's own direct build")
    if not args.output.resolve().is_relative_to((ROOT / "runtime").resolve()) or args.output.exists():
        parser.error("Qualification must be a new file in this worktree's runtime directory")
    before = json.loads(args.source_before.read_text())
    candidate = json.loads(args.candidate.read_text())
    sources, fingerprint = snapshot.source_fingerprint()
    if before["sourceFiles"] != sources or before["sourceFingerprint"] != fingerprint or \
            candidate["sourceFilesAtCapture"] != sources or candidate["sourceFingerprintAtCapture"] != fingerprint:
        raise RuntimeError("Final native sources differ from the before-build or candidate source record")
    current = snapshot.candidate()
    if current["runtimeFiles"] != candidate["runtimeFiles"] or \
            current["runtimeSHA256"] != candidate["runtimeSHA256"]:
        raise RuntimeError("The built runtime changed after candidate hashing")
    if current["sourceFilesAtCapture"] != sources or current["sourceFingerprintAtCapture"] != fingerprint:
        raise RuntimeError("Native sources changed between qualification and repeated candidate hashing")
    tests = native_test_evidence(args.test_log, args.junit)
    record = {
        "schema": 1, "recordedUTC": datetime.now(timezone.utc).isoformat(),
        "runtimeSHA256": candidate["runtimeSHA256"], "runtimeFileCount": len(candidate["runtimeFiles"]),
        "sourceFingerprint": fingerprint, "sourceFiles": sources,
        "sourceUnchangedAcrossBuildTestsAndCandidate": True,
        "sourceBeforeBuildSHA256": digest(args.source_before), "candidateSHA256": digest(args.candidate),
        "buildLogSHA256": digest(args.build_log), "observedBuildExitCode": args.build_exit_code,
        "nativeTests": tests, "matchesSelectedRuntime": candidate["matchesSelectedRuntime"],
        "originalImmutableSnapshot": candidate["selectedRuntime"],
        "immutableSnapshotManifestRewritten": False, "liveProcessQualificationIncluded": False,
        "sourceCaptureIsCompileAttestation": False,
        "note": "This process evidence binds unchanged source fingerprints, the observed successful build exit, six completed test programs and exact built runtime bytes. It does not rewrite immutable history or replace live process/socket/native-participant qualification.",
    }
    final_sources, final_fingerprint = snapshot.source_fingerprint()
    if final_sources != sources or final_fingerprint != fingerprint:
        raise RuntimeError("Native sources changed before final build qualification was written")
    args.output.write_text(json.dumps(record, indent=2) + "\n")
    args.output.chmod(0o600)
    print(json.dumps({"runtimeSHA256": record["runtimeSHA256"], "matchesSelectedRuntime": record["matchesSelectedRuntime"],
                      "nativeChecksPassed": 6, "skipped": 0, "sourceFingerprint": fingerprint,
                      "qualificationSHA256": digest(args.output)}))


if __name__ == "__main__":
    main()
