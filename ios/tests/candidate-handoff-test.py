#!/usr/bin/env python3
"""Execute the real iOS SH-002/009 consumer using original synthetic fixtures."""
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0
import argparse
import copy
import importlib.util
import json
from pathlib import Path
import plistlib
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile

sys.dont_write_bytecode = True
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--shared-contract-root", type=Path, required=True)
parser.add_argument("--identity-contract-root", type=Path, required=True)
parser.add_argument("--sbom-contract-root", type=Path, required=True)
args = parser.parse_args()
ios = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ios / "tools/candidate"))
import verify_candidate_handoff as consumer
from sbom_pair import SBOM_MANIFEST
identity = consumer.identity_contract(args.identity_contract_root)
consumer.pinned_adapter(args.shared_contract_root)
sys.path.insert(0, str(args.shared_contract_root / "tests/device/schema"))
import test_terminal_evidence as evidence_fixture
spec = importlib.util.spec_from_file_location("identity_fixture",
    args.identity_contract_root / "tests/device/schema/artifact-identity/test_identity.py")
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
consumer.verify_release(args.sbom_contract_root, SBOM_MANIFEST,
                        "tools/sbom/verify-sbom-pair.py", executable=False)
sys.path.insert(0, str(args.sbom_contract_root / "provenance"))
spec = importlib.util.spec_from_file_location("sbom_fixture",
    args.sbom_contract_root / "tests/device/schema/artifact-identity/test_sbom_pair.py")
sbom_fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sbom_fixture)

with tempfile.TemporaryDirectory(prefix="ios-handoff-test-") as scratch:
    repo = Path(scratch) / "repo"
    subprocess.run(["git", "init", "-q", str(repo)], check=True, timeout=10)
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=Fixture",
                    "-c", "user.email=fixture@example.invalid", "commit", "-q",
                    "--allow-empty", "-m", "synthetic source"], check=True, timeout=10)
    sha = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True, timeout=10).strip()
    artifact = Path(scratch) / "0001-OverteIOSClient-Release-simulator.zip"
    with zipfile.ZipFile(artifact, "w") as package:
        package.writestr("Overte.app/Info.plist", plistlib.dumps(dict(
            CFBundleExecutable="Overte", CFBundlePackageType="APPL",
            CFBundleSupportedPlatforms=["iPhoneSimulator"], CFBundleIdentifier="org.overte.fixture")))
        executable = zipfile.ZipInfo("Overte.app/Overte")
        executable.external_attr = (stat.S_IFREG | 0o755) << 16
        package.writestr(executable, b"synthetic-not-a-native-binary")
    evidence_fixture.SOURCE, evidence_fixture.ARTIFACT = sha, identity.digest_file(artifact)
    evidence, provenance = evidence_fixture.ContractTests(), fixture.IdentityTests()
    evidence.setUp()
    provenance.setUp()
    try:
        shutil.copy2(artifact, evidence.root)
        manifest = json.loads((ios / "tests/fixtures/io001-candidate/valid.json").read_text())
        manifest["source"]["revision"] = sha
        manifest["artifact"].update(sha256=identity.digest_file(artifact), sizeBytes=artifact.stat().st_size)
        evidence.candidate.write_text(json.dumps(manifest))
        evidence.manifest["candidateSha256"] = identity.digest_file(evidence.candidate)
        normalized = identity.normalized_inputs(provenance.inputs)
        evidence.manifest["normalizedInputsSha256"] = normalized
        for tier in ("cold-full-client-build", "warm-full-client-build"):
            evidence.receipts[tier]["provenance"]["normalizedInputsSha256"] = normalized
        evidence.publish()
        provenance.record.update(sourceRevision=sha, product="ios", artifactSha256=identity.digest_file(artifact))
        sbom_fixture.SOURCE, sbom_fixture.ARTIFACT = sha, identity.digest_file(artifact)
        spdx, cyclone = sbom_fixture.fixture()  # Synthetic format fixture, not a real iOS build.
        for key, value in (("spdx", spdx), ("cyclonedx", cyclone)):
            provenance.files[key].write_text(json.dumps(value))
            provenance.record["evidence"][key] = identity.digest_file(provenance.files[key])
        record, inputs = provenance.root / "record.json", provenance.root / "inputs.json"
        inputs.write_text(json.dumps(provenance.inputs))
        record.write_text(json.dumps(provenance.record))
        command = [sys.executable, str(ios / "tools/candidate/verify_candidate_handoff.py"),
            str(evidence.candidate), "--artifact-root", str(evidence.root), "--repository", str(repo),
            "--expected-source-sha", sha, "--shared-contract-root", str(args.shared_contract_root),
            "--identity-contract-root", str(args.identity_contract_root), "--identity-record", str(record),
            "--sbom-contract-root", str(args.sbom_contract_root),
            "--expected-inputs", str(inputs), "--minimum-version", "1", "--expected-channel", "source-proof"]
        for key, path in provenance.files.items():
            command += ["--" + key, str(path)]
        def run():
            return subprocess.run(command, capture_output=True, text=True, timeout=45)
        success = run()
        assert success.returncode == 0, success.stderr
        result = json.loads(success.stdout)
        assert result["status"] == "IOS_CANDIDATE_BYTES_BOUND_VERIFICATION_PENDING"
        assert result["sharedBuildInputJoin"] == "BOUND_TO_INDEPENDENT_INPUTS"
        assert result["sbomPair"]["status"] == "SBOM_PAIR_VALID_CONTENT_VERIFICATION_PENDING"
        unavailable = subprocess.run([command[0], "-S", *command[1:]],
                                     capture_output=True, text=True, timeout=45)
        assert unavailable.returncode == 1 and unavailable.stderr.strip() == "IOS_CANDIDATE_HANDOFF_REJECTED"
        # Re-read/snapshot must reject bytes changed after the identity check.
        saved_spdx = provenance.files["spdx"].read_bytes()
        provenance.files["spdx"].write_bytes(saved_spdx + b" ")
        try:
            consumer.verify_pair(args.sbom_contract_root, args.identity_contract_root,
                provenance.files["spdx"], provenance.files["cyclonedx"], sha,
                identity.digest_file(artifact), provenance.record["evidence"])
            raise AssertionError("post-identity SBOM replacement accepted")
        except ValueError:
            pass
        provenance.files["spdx"].write_bytes(saved_spdx)
        changed_release = Path(scratch) / "changed-release"
        shutil.copytree(args.sbom_contract_root, changed_release)
        (changed_release / "provenance/sbom_validation.py").write_text("raise RuntimeError('private-canary')")
        tampered_command = command.copy()
        tampered_command[tampered_command.index("--sbom-contract-root") + 1] = str(changed_release)
        tampered = subprocess.run(tampered_command, capture_output=True, text=True, timeout=45)
        assert tampered.returncode == 1 and tampered.stderr.strip() == "IOS_CANDIDATE_HANDOFF_REJECTED"
        # Execute the owned canonical-binding preflight against the SAME actual
        # original consumer and synthetic evidence, not a success-output mock.
        binding_spec = importlib.util.spec_from_file_location("ios_binding_test",
            ios.parent / "tests/device/adapters/ios/binding.py")
        native_binding = importlib.util.module_from_spec(binding_spec)
        binding_spec.loader.exec_module(native_binding)
        native_parser = argparse.ArgumentParser()
        native_binding.configure_parser(native_parser)
        native_args = native_parser.parse_args([
            "--candidate-manifest", command[2], "--expected-artifact-sha256",
            identity.digest_file(artifact), *command[3:]])
        native_binding.candidate_preflight(native_args)
        native_args.expected_artifact_sha256 = "0" * 64
        try:
            native_binding.candidate_preflight(native_args)
            raise AssertionError("foreign independent artifact expectation accepted")
        except ValueError:
            pass
        stage_command = command.copy()
        stage_command[1] = str(ios / "tools/candidate/run_simulator_candidate.py")
        staged = subprocess.run(stage_command, capture_output=True, text=True, timeout=45)
        assert staged.returncode == 0, staged.stderr
        assert json.loads(staged.stdout)["simulator"] == "ARCHIVE_STAGED_NOT_EXECUTED"
        # Coherent hashes cannot turn malformed or mutually inconsistent SBOM
        # content into a pass; the real General CLI must be in the actual path.
        for invalid in ({"testOnly": "not-an-sbom"}, dict(cyclone, specVersion="1.5")):
            provenance.files["cyclonedx"].write_text(json.dumps(invalid))
            changed = copy.deepcopy(provenance.record)
            changed["evidence"]["cyclonedx"] = identity.digest_file(provenance.files["cyclonedx"])
            record.write_text(json.dumps(changed))
            failure = run()
            assert failure.returncode == 1 and failure.stderr.strip() == "IOS_CANDIDATE_HANDOFF_REJECTED"
        provenance.files["cyclonedx"].write_text(json.dumps(cyclone))
        record.write_text(json.dumps(provenance.record))
        # An internally coherent foreign build cohort cannot supply its own
        # expectations, even when source and artifact bytes still match.
        for key in ("normalizedInputsSha256", "toolchainSha256"):
            saved = evidence.manifest[key]
            evidence.manifest[key] = "e" * 64
            for tier in ("cold-full-client-build", "warm-full-client-build"):
                evidence.receipts[tier]["provenance"][key] = "e" * 64
            evidence.publish()
            assert run().returncode == 1
            evidence.manifest[key] = saved
            for tier in ("cold-full-client-build", "warm-full-client-build"):
                evidence.receipts[tier]["provenance"][key] = saved
            evidence.publish()
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
print("PASS iOS original SH-002 v002/SH-009/SBOM CLI join, foreign-cohort and malformed-content negatives; native acceptance pending")
