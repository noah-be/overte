#!/usr/bin/env python3
"""Fail-closed metadata verifier for a credential-free IO-001 candidate."""

# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Any

try:
    from .evidence_binding import EvidenceBindingError, bind_shared_evidence
except ImportError:  # Direct execution from the source tree.
    from evidence_binding import EvidenceBindingError, bind_shared_evidence


CONTRACT = "overte-ios-io001-candidate-v1"
REVISION = re.compile(r"[0-9a-f]{40}")
DIGEST = re.compile(r"[0-9a-f]{64}")
TIER_ID = re.compile(r"[a-z][a-z0-9-]{1,63}")
SAFE_ARTIFACT = re.compile(
    r"[0-9]{4,}-OverteIOSClient-Release-simulator[.]zip"
)
MAX_METADATA_BYTES = 256 * 1024
MAX_ARTIFACT_BYTES = 4 * 1024 * 1024 * 1024
MANDATORY_TIERS = (
    "host-contracts",
    "cold-full-client-build",
    "warm-full-client-build",
    "package-verification",
)
ALLOWED_TOP_LEVEL_KEYS = {"contract", "source", "artifact", "producer", "tiers"}
SOURCE_KEYS = {"revision"}
ARTIFACT_KEYS = {"relativePath", "sha256", "sizeBytes", "kind"}
TIER_KEYS = {"id", "status", "skipReason"}


class CandidateVerificationError(ValueError):
    """Candidate metadata or its bound artifact failed verification."""


def _require_object(value: Any, description: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CandidateVerificationError(f"{description} must be an object")
    return value


def _load_manifest(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise CandidateVerificationError("candidate metadata must be a regular file")
    size = path.stat().st_size
    if size <= 0 or size > MAX_METADATA_BYTES:
        raise CandidateVerificationError("candidate metadata size is out of bounds")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise CandidateVerificationError("candidate metadata is not valid UTF-8 JSON") from error
    payload = _require_object(payload, "candidate metadata root")
    unknown = set(payload) - ALLOWED_TOP_LEVEL_KEYS
    if unknown:
        raise CandidateVerificationError("candidate metadata has unknown top-level fields")
    missing = ALLOWED_TOP_LEVEL_KEYS - set(payload)
    if missing:
        raise CandidateVerificationError("candidate metadata is incomplete")
    return payload


def _safe_artifact_path(root: Path, raw_path: Any) -> Path:
    if not isinstance(raw_path, str) or not raw_path or "\\" in raw_path or "\0" in raw_path:
        raise CandidateVerificationError("artifact relative path is unsafe")
    pure = PurePosixPath(raw_path)
    if pure.is_absolute() or len(pure.parts) != 1 or pure.parts[0] in {".", ".."}:
        raise CandidateVerificationError("artifact relative path is unsafe")
    candidate = root.resolve() / pure.name
    if candidate.is_symlink() or not candidate.is_file():
        raise CandidateVerificationError("candidate artifact is missing or not regular")
    mode = candidate.stat().st_mode
    if not stat.S_ISREG(mode):
        raise CandidateVerificationError("candidate artifact is not a regular file")
    return candidate


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_repository_head(repository: Path, expected_source_sha: str) -> None:
    if not repository.is_dir():
        raise CandidateVerificationError("source repository is unavailable")
    try:
        completed = subprocess.run(
            ["git", "-C", str(repository.resolve()), "rev-parse", "--verify", "HEAD"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
            timeout=10,
        )
    except subprocess.TimeoutExpired as error:
        raise CandidateVerificationError("source repository HEAD lookup timed out") from error
    head = completed.stdout.strip()
    if completed.returncode != 0 or REVISION.fullmatch(head) is None:
        raise CandidateVerificationError("source repository has no verifiable HEAD")
    if head != expected_source_sha:
        raise CandidateVerificationError("expected source SHA does not match repository HEAD")
    try:
        status = subprocess.run(
            [
                "git",
                "-C",
                str(repository.resolve()),
                "status",
                "--porcelain=v1",
                "--untracked-files=all",
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
            timeout=10,
        )
    except subprocess.TimeoutExpired as error:
        raise CandidateVerificationError("source repository status lookup timed out") from error
    if status.returncode != 0:
        raise CandidateVerificationError("source repository status is unavailable")
    if status.stdout:
        raise CandidateVerificationError("source repository has uncommitted content")


def _verify_tiers(raw_tiers: Any) -> tuple[str, ...]:
    if not isinstance(raw_tiers, list) or not raw_tiers:
        raise CandidateVerificationError("candidate tiers must be a non-empty array")
    tiers: dict[str, dict[str, Any]] = {}
    for raw_tier in raw_tiers:
        tier = _require_object(raw_tier, "candidate tier")
        if not {"id", "status"}.issubset(tier) or set(tier) - TIER_KEYS:
            raise CandidateVerificationError("candidate tier fields do not match the contract")
        tier_id = tier.get("id")
        status_value = tier.get("status")
        if not isinstance(tier_id, str) or TIER_ID.fullmatch(tier_id) is None:
            raise CandidateVerificationError("candidate tier has an invalid id")
        if tier_id in tiers:
            raise CandidateVerificationError("candidate tier ids must be unique")
        if status_value not in {"PASS", "FAIL", "SKIPPED"}:
            raise CandidateVerificationError("candidate tier has an invalid status")
        skip_reason = tier.get("skipReason")
        if status_value == "SKIPPED" and (
            not isinstance(skip_reason, str) or not skip_reason.strip()
        ):
            raise CandidateVerificationError(f"tier {tier_id} was skipped without a reason")
        if status_value == "FAIL":
            raise CandidateVerificationError(f"tier {tier_id} failed")
        tiers[tier_id] = tier

    for required in MANDATORY_TIERS:
        if required not in tiers:
            raise CandidateVerificationError(f"missing mandatory tier {required}")
        if tiers[required]["status"] != "PASS":
            raise CandidateVerificationError(f"mandatory tier {required} did not pass")
    return tuple(tier["id"] for tier in raw_tiers)


def verify_candidate(
    manifest_path: Path,
    artifact_root: Path,
    expected_source_sha: str,
    *,
    repository: Path | None = None,
    shared_evidence_adapter: Path | None = None,
    require_shared_evidence: bool = False,
) -> dict[str, Any]:
    """Verify candidate identity and return a privacy-bounded summary."""

    if REVISION.fullmatch(expected_source_sha) is None:
        raise CandidateVerificationError("expected source SHA must be 40 lowercase hex characters")
    if repository is not None:
        _verify_repository_head(repository, expected_source_sha)

    manifest = _load_manifest(manifest_path)
    if manifest["contract"] != CONTRACT:
        raise CandidateVerificationError("candidate metadata contract is unsupported")

    source = _require_object(manifest["source"], "candidate source")
    if set(source) != SOURCE_KEYS:
        raise CandidateVerificationError("candidate source fields do not match the contract")
    revision = source.get("revision")
    if not isinstance(revision, str) or REVISION.fullmatch(revision) is None:
        raise CandidateVerificationError("candidate source revision is invalid")
    if revision != expected_source_sha:
        raise CandidateVerificationError("candidate source revision does not match exact head")

    producer = _require_object(manifest["producer"], "candidate producer")
    expected_producer = {
        "configuration": "Release",
        "sdk": "iphonesimulator",
        "architecture": "arm64",
        "credentialsUsed": False,
    }
    if producer != expected_producer:
        raise CandidateVerificationError("candidate producer is not credential-free Release arm64 simulator")

    artifact_metadata = _require_object(manifest["artifact"], "candidate artifact")
    if set(artifact_metadata) != ARTIFACT_KEYS:
        raise CandidateVerificationError("candidate artifact fields do not match the contract")
    expected_digest = artifact_metadata.get("sha256")
    expected_size = artifact_metadata.get("sizeBytes")
    if not isinstance(expected_digest, str) or DIGEST.fullmatch(expected_digest) is None:
        raise CandidateVerificationError("candidate artifact SHA-256 is invalid")
    if not isinstance(expected_size, int) or isinstance(expected_size, bool):
        raise CandidateVerificationError("candidate artifact size is invalid")
    if not 1 <= expected_size <= MAX_ARTIFACT_BYTES:
        raise CandidateVerificationError("candidate artifact size is out of bounds")
    if artifact_metadata.get("kind") != "full-client-simulator":
        raise CandidateVerificationError("candidate artifact kind is not full-client-simulator")
    relative_path = artifact_metadata.get("relativePath")
    if not isinstance(relative_path, str) or SAFE_ARTIFACT.fullmatch(relative_path) is None:
        raise CandidateVerificationError("candidate artifact name does not match the IO-001 contract")
    artifact = _safe_artifact_path(artifact_root, relative_path)
    if artifact.stat().st_size != expected_size:
        raise CandidateVerificationError("candidate artifact size mismatch")
    actual_digest = _sha256(artifact)
    if actual_digest != expected_digest:
        raise CandidateVerificationError("candidate artifact SHA-256 mismatch")

    tier_ids = _verify_tiers(manifest["tiers"])
    try:
        binding = bind_shared_evidence(
            shared_evidence_adapter,
            manifest_path,
            revision,
            actual_digest,
        )
    except EvidenceBindingError as error:
        raise CandidateVerificationError(str(error)) from error
    if require_shared_evidence and binding != "BOUND":
        raise CandidateVerificationError("accepted SH-002 evidence adapter is required")

    return {
        "status": "PASS",
        "sourceRevision": revision,
        "artifactSha256": actual_digest,
        "mandatoryTiers": list(MANDATORY_TIERS),
        "observedTierIds": list(tier_ids),
        "sharedEvidence": binding,
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--artifact-root", required=True, type=Path)
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--repository", required=True, type=Path)
    parser.add_argument("--shared-evidence-adapter", type=Path)
    parser.add_argument("--require-shared-evidence", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    try:
        summary = verify_candidate(
            args.manifest,
            args.artifact_root,
            args.expected_source_sha,
            repository=args.repository,
            shared_evidence_adapter=args.shared_evidence_adapter,
            require_shared_evidence=args.require_shared_evidence,
        )
    except CandidateVerificationError as error:
        print(f"candidate verification failed: {error}", file=sys.stderr)
        return 1
    json.dump(summary, sys.stdout, sort_keys=True, separators=(",", ":"))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
