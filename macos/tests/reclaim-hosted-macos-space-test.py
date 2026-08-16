#!/usr/bin/env python3
"""Hermetic safety contract for hosted macOS build-space reclamation."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "macos/ci/reclaim-hosted-macos-space.sh"

environment = os.environ.copy()
environment["OVERTE_MACOS_TEST_DEVELOPER_DIR"] = "/Applications/Xcode_Test.app/Contents/Developer"
result = subprocess.run(
    [str(SCRIPT), "--dry-run"], text=True, capture_output=True, env=environment, check=False
)
assert result.returncode == 0, result.stdout + result.stderr
targets = result.stdout.splitlines()
assert len(targets) == 13
assert len(set(targets)) == len(targets)
assert all(target.startswith((
    "/Applications/Xcode_Test.app/Contents/Developer/",
    "/Library/Developer/CoreSimulator/",
)) for target in targets)
assert not any("MacOSX.platform" in target for target in targets)
assert not any(target in ("/", "/Applications", "/Library", "/Users") for target in targets)

unsafe_environment = environment.copy()
unsafe_environment["OVERTE_MACOS_TEST_DEVELOPER_DIR"] = "/tmp/not-xcode"
unsafe = subprocess.run(
    [str(SCRIPT), "--dry-run"], text=True, capture_output=True,
    env=unsafe_environment, check=False,
)
assert unsafe.returncode != 0
assert "refusing unexpected Xcode developer directory" in unsafe.stderr

source = SCRIPT.read_text(encoding="utf-8")
for contract in (
    '"${RUNNER_ENVIRONMENT:-}" == github-hosted',
    'OVERTE_ALLOW_EPHEMERAL_RUNNER_CLEANUP',
    'sudo rm -rf -- "$target"',
    'validate_target "$target"',
):
    assert contract in source

print("hosted macOS build-space reclamation contract valid")
