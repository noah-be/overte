#!/usr/bin/env python3
"""Focused host tests for the credential-free IO-001 candidate verifier."""

# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parents[2]
CANDIDATE_TOOLS = REPOSITORY / "ios/tools/candidate"
FIXTURES = Path(__file__).with_name("fixtures") / "io001-candidate"
EXPECTED_SOURCE = "a" * 40
sys.path.insert(0, str(CANDIDATE_TOOLS))

import evidence_binding  # noqa: E402
import verify_io001_candidate as verifier  # noqa: E402


def materialize(root: Path, fixture_name: str) -> Path:
    shutil.copy2(FIXTURES / "0001-OverteIOSClient-Release-simulator.zip", root)
    manifest = root / "candidate.json"
    shutil.copy2(FIXTURES / fixture_name, manifest)
    return manifest


def expect_rejection(fixture_name: str, expected: str) -> None:
    with tempfile.TemporaryDirectory(prefix="io001-candidate-reject-") as temporary:
        root = Path(temporary)
        manifest = materialize(root, fixture_name)
        try:
            verifier.verify_candidate(manifest, root, EXPECTED_SOURCE)
        except verifier.CandidateVerificationError as error:
            assert expected in str(error), (fixture_name, str(error))
        else:
            raise AssertionError(f"unsafe fixture accepted: {fixture_name}")


def write_adapter(path: Path, exit_code: int) -> None:
    path.write_text(
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "required = {'--candidate-metadata', '--expected-source-sha', "
        "'--expected-artifact-sha256'}\n"
        f"raise SystemExit({exit_code} if required.issubset(sys.argv) else 12)\n",
        encoding="utf-8",
    )
    path.chmod(0o700)


def create_source_repository(path: Path) -> tuple[Path, str]:
    source = path / "source"
    source.mkdir()
    subprocess.run(["git", "init", "-q", str(source)], check=True, timeout=10)
    subprocess.run(
        ["git", "-C", str(source), "config", "user.name", "IO-001 Fixture"],
        check=True,
        timeout=10,
    )
    subprocess.run(
        ["git", "-C", str(source), "config", "user.email", "fixture@example.invalid"],
        check=True,
        timeout=10,
    )
    tracked = source / "tracked.txt"
    tracked.write_text("exact source\n", encoding="utf-8")
    subprocess.run(
        ["git", "-C", str(source), "add", "tracked.txt"], check=True, timeout=10
    )
    subprocess.run(
        ["git", "-C", str(source), "commit", "-q", "-m", "fixture source"],
        check=True,
        timeout=10,
    )
    head = subprocess.run(
        ["git", "-C", str(source), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    ).stdout.strip()
    return source, head


with tempfile.TemporaryDirectory(prefix="io001-candidate-valid-") as temporary:
    root = Path(temporary)
    manifest = materialize(root, "valid.json")
    summary = verifier.verify_candidate(manifest, root, EXPECTED_SOURCE)
    assert summary["status"] == "PASS"
    assert summary["sourceRevision"] == EXPECTED_SOURCE
    assert summary["sharedEvidence"] == "DEFERRED"
    assert tuple(summary["mandatoryTiers"]) == verifier.MANDATORY_TIERS

expect_rejection("stale-sha.json", "source revision does not match exact head")
expect_rejection("wrong-artifact.json", "artifact SHA-256 mismatch")
expect_rejection("missing-mandatory-tier.json", "missing mandatory tier")
expect_rejection("unexplained-skip.json", "skipped without a reason")

with tempfile.TemporaryDirectory(prefix="io001-candidate-strict-") as temporary:
    root = Path(temporary)
    manifest = materialize(root, "valid.json")
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["tiers"].append(
        {
            "id": "optional-diagnostics",
            "status": "SKIPPED",
            "skipReason": "not part of the credential-free candidate contract",
        }
    )
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    verifier.verify_candidate(manifest, root, EXPECTED_SOURCE)

    payload["tiers"][-1] = {"id": "optional-diagnostics", "status": "FAIL"}
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    try:
        verifier.verify_candidate(manifest, root, EXPECTED_SOURCE)
    except verifier.CandidateVerificationError as error:
        assert "optional-diagnostics failed" in str(error)
    else:
        raise AssertionError("failed optional tier was accepted")

    payload = json.loads((FIXTURES / "valid.json").read_text(encoding="utf-8"))
    payload["source"]["unreviewedField"] = "must fail closed"
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    try:
        verifier.verify_candidate(manifest, root, EXPECTED_SOURCE)
    except verifier.CandidateVerificationError as error:
        assert "source fields do not match" in str(error)
    else:
        raise AssertionError("unknown source field was accepted")

    payload = json.loads((FIXTURES / "valid.json").read_text(encoding="utf-8"))
    payload["artifact"]["relativePath"] = "candidate.zip"
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    try:
        verifier.verify_candidate(manifest, root, EXPECTED_SOURCE)
    except verifier.CandidateVerificationError as error:
        assert "artifact name does not match" in str(error)
    else:
        raise AssertionError("unbound artifact name was accepted")

with tempfile.TemporaryDirectory(prefix="io001-candidate-head-") as temporary:
    root = Path(temporary)
    manifest = materialize(root, "valid.json")
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    source, head = create_source_repository(root)
    payload["source"]["revision"] = head
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    summary = verifier.verify_candidate(
        manifest,
        root,
        head,
        repository=source,
    )
    assert summary["sourceRevision"] == head

    (source / "tracked.txt").write_text("dirty source\n", encoding="utf-8")
    try:
        verifier.verify_candidate(manifest, root, head, repository=source)
    except verifier.CandidateVerificationError as error:
        assert "uncommitted content" in str(error)
    else:
        raise AssertionError("dirty source repository was accepted")
    subprocess.run(
        ["git", "-C", str(source), "restore", "tracked.txt"], check=True, timeout=10
    )
    untracked = source / "untracked.txt"
    untracked.write_text("untracked build input\n", encoding="utf-8")
    try:
        verifier.verify_candidate(manifest, root, head, repository=source)
    except verifier.CandidateVerificationError as error:
        assert "uncommitted content" in str(error)
    else:
        raise AssertionError("untracked source content was accepted")
    untracked.unlink()
    (source / "tracked.txt").write_text("new exact source\n", encoding="utf-8")
    subprocess.run(
        ["git", "-C", str(source), "commit", "-qam", "advance source"],
        check=True,
        timeout=10,
    )
    try:
        verifier.verify_candidate(manifest, root, head, repository=source)
    except verifier.CandidateVerificationError as error:
        assert "does not match repository HEAD" in str(error)
    else:
        raise AssertionError("stale expected source HEAD was accepted")

with tempfile.TemporaryDirectory(prefix="io001-candidate-adapter-") as temporary:
    root = Path(temporary)
    manifest = materialize(root, "valid.json")
    try:
        verifier.verify_candidate(
            manifest,
            root,
            EXPECTED_SOURCE,
            require_shared_evidence=True,
        )
    except verifier.CandidateVerificationError as error:
        assert "accepted SH-002 evidence adapter is required" in str(error)
    else:
        raise AssertionError("required shared evidence was silently deferred")

    accepted = root / "accepted-adapter.py"
    rejected = root / "rejected-adapter.py"
    write_adapter(accepted, 0)
    write_adapter(rejected, 7)
    summary = verifier.verify_candidate(
        manifest,
        root,
        EXPECTED_SOURCE,
        shared_evidence_adapter=accepted,
        require_shared_evidence=True,
    )
    assert summary["sharedEvidence"] == "BOUND"
    try:
        verifier.verify_candidate(
            manifest,
            root,
            EXPECTED_SOURCE,
            shared_evidence_adapter=rejected,
        )
    except verifier.CandidateVerificationError as error:
        assert str(error) == "shared evidence adapter rejected the candidate"
    else:
        raise AssertionError("rejected shared evidence adapter was accepted")

    assert "schema" not in evidence_binding.DEFERRED_INPUT_CONTRACT.lower()
    assert "SH-002" in evidence_binding.DEFERRED_INPUT_CONTRACT
    assert "executable" in evidence_binding.DEFERRED_INPUT_CONTRACT

with tempfile.TemporaryDirectory(prefix="io001-candidate-cli-") as temporary:
    root = Path(temporary)
    manifest = materialize(root, "valid.json")
    source, head = create_source_repository(root)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["source"]["revision"] = head
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    completed = subprocess.run(
        [
            sys.executable,
            str(CANDIDATE_TOOLS / "verify_io001_candidate.py"),
            str(manifest),
            "--artifact-root",
            str(root),
            "--expected-source-sha",
            head,
            "--repository",
            str(source),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
    cli_summary = json.loads(completed.stdout)
    assert cli_summary["sharedEvidence"] == "DEFERRED"
    assert str(root) not in completed.stdout

    missing_repository = subprocess.run(
        [
            sys.executable,
            str(CANDIDATE_TOOLS / "verify_io001_candidate.py"),
            str(manifest),
            "--artifact-root",
            str(root),
            "--expected-source-sha",
            head,
        ],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=30,
    )
    assert missing_repository.returncode == 2

print("PASS credential-free IO-001 candidate verifier fixtures")
