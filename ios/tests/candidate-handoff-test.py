#!/usr/bin/env python3
"""Execute the real iOS SH-002/009 consumer using original synthetic fixtures."""
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0
import argparse
import copy
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--shared-contract-root", type=Path, required=True)
parser.add_argument("--identity-contract-root", type=Path, required=True)
args = parser.parse_args()
ios = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ios / "tools/candidate"))
import verify_candidate_handoff as consumer
identity = consumer.identity_contract(args.identity_contract_root)
consumer.pinned_adapter(args.shared_contract_root)
sys.path.insert(0, str(args.shared_contract_root / "tests/device/schema"))
import test_terminal_evidence as evidence_fixture
spec = importlib.util.spec_from_file_location("identity_fixture",
    args.identity_contract_root / "tests/device/schema/artifact-identity/test_identity.py")
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)

with tempfile.TemporaryDirectory(prefix="ios-handoff-test-") as scratch:
    repo = Path(scratch) / "repo"
    subprocess.run(["git", "init", "-q", str(repo)], check=True, timeout=10)
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=Fixture",
                    "-c", "user.email=fixture@example.invalid", "commit", "-q",
                    "--allow-empty", "-m", "synthetic source"], check=True, timeout=10)
    sha = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True, timeout=10).strip()
    artifact = ios / "tests/fixtures/io001-candidate/0001-OverteIOSClient-Release-simulator.zip"
    evidence_fixture.SOURCE, evidence_fixture.ARTIFACT = sha, identity.digest_file(artifact)
    evidence, provenance = evidence_fixture.ContractTests(), fixture.IdentityTests()
    evidence.setUp()
    provenance.setUp()
    try:
        shutil.copy2(artifact, evidence.root)
        manifest = json.loads((ios / "tests/fixtures/io001-candidate/valid.json").read_text())
        manifest["source"]["revision"] = sha
        evidence.candidate.write_text(json.dumps(manifest))
        evidence.manifest["candidateSha256"] = identity.digest_file(evidence.candidate)
        normalized = identity.normalized_inputs(provenance.inputs)
        evidence.manifest["normalizedInputsSha256"] = normalized
        for tier in ("cold-full-client-build", "warm-full-client-build"):
            evidence.receipts[tier]["provenance"]["normalizedInputsSha256"] = normalized
        evidence.publish()
        provenance.record.update(sourceRevision=sha, product="ios", artifactSha256=identity.digest_file(artifact))
        record, inputs = provenance.root / "record.json", provenance.root / "inputs.json"
        inputs.write_text(json.dumps(provenance.inputs))
        record.write_text(json.dumps(provenance.record))
        command = [sys.executable, str(ios / "tools/candidate/verify_candidate_handoff.py"),
            str(evidence.candidate), "--artifact-root", str(evidence.root), "--repository", str(repo),
            "--expected-source-sha", sha, "--shared-contract-root", str(args.shared_contract_root),
            "--identity-contract-root", str(args.identity_contract_root), "--identity-record", str(record),
            "--expected-inputs", str(inputs), "--minimum-version", "1", "--expected-channel", "source-proof"]
        for key, path in provenance.files.items():
            command += ["--" + key, str(path)]
        def run():
            return subprocess.run(command, capture_output=True, text=True, timeout=45)
        success = run()
        assert success.returncode == 0, success.stderr
        result = json.loads(success.stdout)
        assert result["status"] == "IOS_CANDIDATE_BYTES_BOUND_VERIFICATION_PENDING"
        assert result["sharedBuildInputJoin"] == "PENDING_SHARED_CONTRACT"
        for mutation in ({"product": "android-phone"}, {"channel": "internal-candidate"},
                         {"versionCode": 1}, {"artifactSha256": "f" * 64},
                         {"inputs": dict(provenance.inputs, toolchain="f" * 64)},
                         {"signature": {"state": "verified", "receiptSha256": "f" * 64}}):
            changed = copy.deepcopy(provenance.record)
            changed.update(mutation)
            record.write_text(json.dumps(changed))
            failure = run()
            assert failure.returncode == 1 and failure.stderr.strip() == "IOS_CANDIDATE_HANDOFF_REJECTED"
        record.write_text(json.dumps(provenance.record))
        provenance.files["generatedOutputs"].write_text("foreign bytes")
        assert run().returncode == 1
    finally:
        evidence.doCleanups()
        provenance.doCleanups()
print("PASS iOS original SH-002/009 consumer; build-input join/native acceptance remain pending")
