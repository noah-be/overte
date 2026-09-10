#!/usr/bin/env python3
"""End-to-end iOS consumer test using General's pinned synthetic receipt fixture."""
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True  # importing fixtures must not mutate the release

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--shared-contract-root", type=Path, required=True)
args = parser.parse_args()
ios = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ios / "tools/candidate"))
import verify_io001_release as consumer

consumer.pinned_adapter(args.shared_contract_root)
sys.path.insert(0, str(args.shared_contract_root / "tests/device/schema"))
import test_terminal_evidence as fixture

with tempfile.TemporaryDirectory(prefix="ios-shared-consumer-") as scratch:
    root = Path(scratch)
    repo = root / "source"
    subprocess.run(["git", "init", "-q", str(repo)], check=True, timeout=10)
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=Fixture",
                    "-c", "user.email=fixture@example.invalid", "commit", "-q",
                    "--allow-empty", "-m", "synthetic consumer source"], check=True, timeout=10)
    sha = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True, timeout=10).strip()
    fixture.SOURCE = sha
    artifact = ios / "tests/fixtures/io001-candidate/0001-OverteIOSClient-Release-simulator.zip"
    fixture.ARTIFACT = hashlib.sha256(artifact.read_bytes()).hexdigest()
    case = fixture.ContractTests()
    case.setUp()
    try:
        manifest = json.loads((ios / "tests/fixtures/io001-candidate/valid.json").read_text())
        manifest["source"]["revision"] = sha
        # Shared owns all receipt/schema construction in this test.
        shutil.copy2(artifact, case.root)
        case.candidate.write_text(json.dumps(manifest))
        case.manifest["candidateSha256"] = hashlib.sha256(case.candidate.read_bytes()).hexdigest()
        case.publish()
        command = [sys.executable, str(ios / "tools/candidate/verify_io001_release.py"),
                   str(case.candidate), "--artifact-root", str(case.root), "--repository", str(repo),
                   "--expected-source-sha", sha, "--shared-contract-root", str(args.shared_contract_root)]
        success = subprocess.run(command, capture_output=True, text=True, timeout=40)
        assert success.returncode == 0, success.stderr
        assert json.loads(success.stdout)["sharedEvidence"] == "BOUND"
        case.sidecar.unlink()
        rejected = subprocess.run(command, capture_output=True, text=True, timeout=40)
        assert rejected.returncode == 1 and "rejected" in rejected.stderr
        assert str(case.root) not in rejected.stderr
    finally:
        case.doCleanups()

    copied = root / "changed-contract"
    shutil.copytree(args.shared_contract_root, copied, ignore=shutil.ignore_patterns("__pycache__"))
    module = copied / "tests/device/schema/terminal_evidence.py"
    module.write_text(module.read_text() + "\n# tampered\n")
    try:
        consumer.pinned_adapter(copied)
        raise AssertionError("changed Shared module was accepted")
    except ValueError as error:
        assert str(error) == "SHARED_SOURCE_DIGEST"
    clean_copy = root / "extra-contract"
    shutil.copytree(args.shared_contract_root, clean_copy, ignore=shutil.ignore_patterns("__pycache__"))
    for name in ("json.py", "terminal_evidence.pyc"):
        extra = clean_copy / "tests/device/schema" / name
        extra.write_text("raise RuntimeError('UNDECLARED-CANARY')\n")
        try:
            consumer.pinned_adapter(clean_copy)
        except ValueError as error:
            assert str(error) == "SHARED_UNDECLARED_SOURCE"
        else:
            raise AssertionError("unverified import source accepted")
        extra.unlink()
print("PASS pinned Shared consumer: synthetic binding, missing sidecar rejection, source tamper rejection")
