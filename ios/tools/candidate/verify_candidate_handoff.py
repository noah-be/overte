#!/usr/bin/env python3
"""Require SH-002 evidence and SH-009 byte/input identity for an iOS candidate.

Offline binding only, not signing, SBOM semantic completeness or node acceptance.
SH-002 v001 cannot yet join its build-input cohort to SH-009's frozen input map;
that pending Shared hook is reported explicitly and forbids final handoff use.
Expected inputs, channel and minimum version come from the frozen build request,
never from the producer's identity record. No Common schema is copied here.
"""
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0
import argparse
import hashlib
import json
from pathlib import Path
import sys
import types

import verify_io001_candidate as candidate
from verify_io001_release import pinned_adapter
from shared_release import verify_release

IDENTITY_MANIFEST = "0938dcc56f67b30c4402d2bb56719b84f15628b1e3d6b5bc617bf4b93b01a1d4"
IDENTITY_SOURCE = "fc4ac96c70987179bfc62c02106ba3ab0d28277aef55f6a8f0b0065e2ca4cdbd"


def identity_contract(root: Path):
    path = verify_release(root, IDENTITY_MANIFEST, "provenance/artifact_identity.py", executable=False)
    source = path.read_bytes()
    if hashlib.sha256(source).hexdigest() != IDENTITY_SOURCE:
        raise ValueError("IDENTITY_SOURCE_CHANGED")
    # Execute the exact verified source, never an external precompiled cache.
    module = types.ModuleType("overte_sh009_identity_v001")
    module.__file__ = str(path)
    exec(compile(source, str(path), "exec"), module.__dict__)
    return module


def main(argv: list[str]) -> int:
    preliminary = argparse.ArgumentParser(add_help=False)
    preliminary.add_argument("--identity-contract-root", type=Path, required=True)
    known, _ = preliminary.parse_known_args(argv)
    try:
        identity = identity_contract(known.identity_contract_root)
    except (OSError, ValueError):
        print("IOS_CANDIDATE_HANDOFF_REJECTED", file=sys.stderr)
        return 1
    parser = argparse.ArgumentParser(description=__doc__, parents=[preliminary])
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--shared-contract-root", type=Path, required=True)
    parser.add_argument("--identity-record", type=Path, required=True)
    parser.add_argument("--expected-inputs", type=Path, required=True)
    parser.add_argument("--minimum-version", type=int, required=True)
    parser.add_argument("--expected-channel", choices=("source-proof", "internal-candidate"), required=True)
    for key in identity.EVIDENCE_KEYS:
        parser.add_argument("--" + key, type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        evidence = pinned_adapter(args.shared_contract_root)
        binding = candidate.verify_candidate(args.manifest, args.artifact_root,
            args.expected_source_sha, repository=args.repository,
            shared_evidence_adapter=evidence, require_shared_evidence=True)
        metadata = candidate._load_manifest(args.manifest)
        artifact = candidate._safe_artifact_path(args.artifact_root, metadata["artifact"]["relativePath"])
        record = identity.read_record(args.identity_record)
        # Shared v001 is platform-neutral; the actual iOS caller adds its
        # expected product/channel, without changing Common record semantics.
        if record.get("product") != "ios" or record.get("channel") != args.expected_channel:
            raise ValueError("IOS_IDENTITY_CONTEXT")
        result = identity.validate(record, artifact,
            {key: getattr(args, key) for key in identity.EVIDENCE_KEYS},
            args.expected_source_sha, identity.read_record(args.expected_inputs), args.minimum_version)
        if result["artifactSha256"] != binding["artifactSha256"]:
            raise ValueError("IOS_IDENTITY_ARTIFACT_CHANGED")
        candidate._verify_repository_head(args.repository, args.expected_source_sha)
    except (OSError, ValueError, TypeError, KeyError):
        print("IOS_CANDIDATE_HANDOFF_REJECTED", file=sys.stderr)
        return 1
    print(json.dumps({"status": "IOS_CANDIDATE_BYTES_BOUND_VERIFICATION_PENDING",
        "sharedEvidence": binding["sharedEvidence"], "artifactIdentity": result,
        "sharedBuildInputJoin": "PENDING_SHARED_CONTRACT"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
