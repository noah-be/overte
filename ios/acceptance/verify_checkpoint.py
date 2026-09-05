#!/usr/bin/env python3
"""Bind completed iOS runner outputs to the whole pinned checkpoint scope.

Offline only. SH-004 verifies identity/integrity, not install truth, form factor,
pixels, or node acceptance. This consumer cannot schedule or contact a device.
"""
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools/candidate"))
from shared_release import verify_release

MANIFEST_SHA256 = "d92c7710551fe134029d2243cea84350a18000934acbd765bd1ef138b3cfa85b"
ENTRYPOINT = "tests/device/verify-result.py"
SCOPES = ("e2e-core", "domain-smoke", "render-health", "interaction-smoke", "tablet-e2e")


def checkpoint_modules(root: Path, scope: str) -> list[str]:
    # Read the original, pinned catalog. Do not maintain a second result schema
    # or accept a caller-selected successful subset of this checkpoint.
    catalog = json.loads((root / "tests/device/catalog.json").read_text())
    modules = [item["id"] for item in catalog["modules"] if scope in item["suites"]]
    if scope not in SCOPES or not modules:
        raise ValueError("CHECKPOINT_SCOPE")
    return modules


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shared-contract-root", type=Path, required=True)
    parser.add_argument("--result-dir", type=Path, required=True)
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--expected-artifact-sha256", required=True)
    parser.add_argument("--checkpoint", choices=SCOPES, required=True)
    args = parser.parse_args(argv)
    try:
        script = verify_release(args.shared_contract_root, MANIFEST_SHA256, ENTRYPOINT, executable=False)
        modules = checkpoint_modules(args.shared_contract_root, args.checkpoint)
        command = [sys.executable, str(script), "--result-dir", str(args.result_dir),
                   "--expected-source-sha", args.expected_source_sha,
                   "--expected-artifact-sha256", args.expected_artifact_sha256,
                   "--expected-adapter", "appium-ios", "--expected-platform", "ios",
                   "--device-class", "physical"]
        for module in modules:
            command += ["--required-module", module]
        with tempfile.TemporaryDirectory(prefix="ios-result-import-") as scratch:
            environment = os.environ.copy()
            environment["PYTHONDONTWRITEBYTECODE"] = "1"
            environment["PYTHONPYCACHEPREFIX"] = scratch
            result = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                    stderr=subprocess.DEVNULL, text=True, timeout=30, env=environment)
        if result.returncode != 0 or len(result.stdout) > 4096:
            raise ValueError("CHECKPOINT_REJECTED")
    except (OSError, ValueError, subprocess.TimeoutExpired):
        print("IOS_CHECKPOINT_REJECTED", file=sys.stderr)
        return 1
    sys.stdout.write(result.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
