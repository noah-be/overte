#!/usr/bin/env python3
"""Require SH-002 evidence and SH-009 byte/input identity for an iOS candidate.

Offline binding only, not signing, SBOM semantic completeness or node acceptance.
SH-002 v002 joins its build-input cohort to SH-009's independently frozen map.
Expected inputs, channel and minimum version come from the frozen build request,
never from the producer's identity record. No Common schema is copied here.
"""
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0
import argparse
import hashlib
import json
from pathlib import Path
import plistlib
import subprocess
import sys
import tempfile
import types
import zipfile

import verify_io001_candidate as candidate
from sbom_pair import verify_pair
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
    parser.add_argument("--sbom-contract-root", type=Path, required=True)
    parser.add_argument("--expected-inputs", type=Path, required=True)
    parser.add_argument("--minimum-version", type=int, required=True)
    parser.add_argument("--expected-channel", choices=("source-proof", "internal-candidate"), required=True)
    parser.add_argument("--stage-simulator", action="store_true")
    parser.add_argument("--execute-simulator", "--execute", action="store_true")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--online-domain-uuid")
    for key in identity.EVIDENCE_KEYS:
        parser.add_argument("--" + key, type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        evidence = pinned_adapter(args.shared_contract_root)
        metadata = candidate._load_manifest(args.manifest)
        artifact = candidate._safe_artifact_path(args.artifact_root, metadata["artifact"]["relativePath"])
        record = identity.read_record(args.identity_record)
        # Shared v001 is platform-neutral; the actual iOS caller adds its
        # expected product/channel, without changing Common record semantics.
        if record.get("product") != "ios" or record.get("channel") != args.expected_channel:
            raise ValueError("IOS_IDENTITY_CONTEXT")
        inputs = identity.read_record(args.expected_inputs)
        result = identity.validate(record, artifact,
            {key: getattr(args, key) for key in identity.EVIDENCE_KEYS},
            args.expected_source_sha, inputs, args.minimum_version)
        binding = candidate.verify_candidate(args.manifest, args.artifact_root,
            args.expected_source_sha, repository=args.repository,
            shared_evidence_adapter=evidence, require_shared_evidence=True,
            expected_normalized_inputs_sha256=identity.normalized_inputs(inputs),
            expected_toolchain_sha256=inputs["toolchain"])
        if result["artifactSha256"] != binding["artifactSha256"]:
            raise ValueError("IOS_IDENTITY_ARTIFACT_CHANGED")
        sbom = verify_pair(args.sbom_contract_root, args.identity_contract_root,
            args.spdx, args.cyclonedx, args.expected_source_sha,
            result["artifactSha256"], record["evidence"])
        candidate._verify_repository_head(args.repository, args.expected_source_sha)
        simulator_state = "NOT_EXECUTED"
        if args.stage_simulator or args.execute_simulator:
            from run_simulator_candidate import stage_archive, simulator
            if args.execute_simulator and (args.output_dir is None or args.online_domain_uuid is None):
                raise ValueError("SIMULATOR_PARAMETERS")
            with tempfile.TemporaryDirectory(prefix="ios-bound-candidate-") as scratch:
                app, bundle = stage_archive(artifact, Path(scratch), result["artifactSha256"])
                candidate._verify_repository_head(args.repository, args.expected_source_sha)
                simulator_state = "ARCHIVE_STAGED_NOT_EXECUTED"
                if args.execute_simulator:
                    plan = Path(__file__).resolve().parents[2] / "tests/io001-simulator-cases.json"
                    simulator.execute_plan(plan, app, bundle, args.output_dir, args.online_domain_uuid)
                    simulator_state = "SIMULATOR_CASES_COMPLETED_NOT_NODE_ACCEPTED"
    except (OSError, ValueError, TypeError, KeyError, zipfile.BadZipFile,
            plistlib.InvalidFileException, subprocess.SubprocessError, RuntimeError):
        print("IOS_CANDIDATE_HANDOFF_REJECTED", file=sys.stderr)
        return 1
    print(json.dumps({"status": "IOS_CANDIDATE_BYTES_BOUND_VERIFICATION_PENDING",
        "sharedEvidence": binding["sharedEvidence"], "artifactIdentity": result,
        "sharedBuildInputJoin": "BOUND_TO_INDEPENDENT_INPUTS", "sbomPair": sbom,
        "simulator": simulator_state}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
