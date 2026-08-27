#!/usr/bin/env python3
"""Record the explicit human boundary after local Personal Team re-signing."""

# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path


KIT_CONTRACT = "overte-ios-personal-team-e2e-kit-v2"
HANDOFF_CONTRACT = "overte-ios-personal-team-signed-handoff-v1"
OVERTE_SIGNED_NAME = "Overte-PersonalTeam-E2E-signed.ipa"
WDA_SIGNED_NAME = "WebDriverAgentRunner-16.8.0-PersonalTeam-signed.ipa"
EXPECTED_IDS = {
    "overte": "org.overte.interface.e2e",
    "wdaRunner": "org.overte.WebDriverAgentRunner.xctrunner",
    "wdaXCTest": "org.overte.WebDriverAgentRunner",
}
WDA_CREDENTIAL_FREE_SIGNING = {
    "nestedBundle": "PlugIns/WebDriverAgentRunner.xctest",
    "method": "ad-hoc",
    "outerRunnerBundleCodeResourcesPresent": False,
    "outerRunnerNewAdHocSignatureApplied": False,
    "outerRunnerProvisioned": False,
    "signer": "rcodesign",
    "signerVersion": "0.29.0",
    "signerExecutableSha256":
        "dab9a7465f96aba3c81e793775510f745b91a46b6418e89f7317b5d8fc7bcea2",
}
MAX_IPA_BYTES = 6 * 1024 * 1024 * 1024
CHECKOUT_ROOT = Path(__file__).resolve().parents[2]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def require_regular_file(
    path: Path, expected_name: str, label: str, *, private: bool = False
) -> None:
    if has_symlink_component(path):
        raise ValueError(f"{label} path must be symlink-free")
    try:
        mode = path.lstat().st_mode
    except OSError as error:
        raise ValueError(f"{label} is unavailable") from error
    if path.name != expected_name:
        raise ValueError(f"{label} must be named {expected_name}")
    if not stat.S_ISREG(mode) or path.is_symlink():
        raise ValueError(f"{label} must be a regular file")
    if path.stat().st_size <= 0 or path.stat().st_size > MAX_IPA_BYTES:
        raise ValueError(f"{label} size is invalid")
    if private and stat.S_IMODE(mode) & 0o077:
        raise ValueError(f"{label} permissions must not grant group or other access")
    if private and path.stat().st_uid != os.getuid():
        raise ValueError(f"{label} must be owned by the current user")
    if private:
        try:
            path.resolve(strict=True).relative_to(CHECKOUT_ROOT.resolve(strict=True))
        except ValueError:
            pass
        else:
            raise ValueError(f"{label} must be outside the checkout")


def has_symlink_component(path: Path) -> bool:
    absolute = path.absolute()
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        try:
            if current.is_symlink():
                return True
        except OSError:
            return True
    return False


def require_private_output_parent(output: Path) -> Path:
    parent = output.parent
    if has_symlink_component(parent):
        raise ValueError("attestation output parent must be symlink-free")
    try:
        resolved = parent.resolve(strict=True)
        mode = resolved.stat().st_mode
    except OSError as error:
        raise ValueError("attestation output parent must already exist") from error
    try:
        resolved.relative_to(CHECKOUT_ROOT.resolve(strict=True))
    except ValueError:
        pass
    else:
        raise ValueError("attestation output parent must be outside the checkout")
    if not stat.S_ISDIR(mode) or stat.S_IMODE(mode) & 0o077:
        raise ValueError("attestation output parent permissions must be 0700 or stricter")
    if resolved.stat().st_uid != os.getuid():
        raise ValueError("attestation output parent must be owned by the current user")
    return resolved


def parse_time(value: str) -> dt.datetime:
    if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z", value) is None:
        raise ValueError("createdAt must be a second-precision UTC timestamp")
    try:
        return dt.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=dt.timezone.utc
        )
    except ValueError as error:
        raise ValueError("createdAt is invalid") from error


def create_attestation(
    unsigned_kit: Path,
    overte_ipa: Path,
    wda_ipa: Path,
    output: Path,
    created_at: str,
    accepted_boundary: bool,
    signed_from_reviewed_kit: bool,
    same_personal_team: bool,
) -> dict:
    if not (accepted_boundary and signed_from_reviewed_kit and same_personal_team):
        raise ValueError("all explicit human signing attestations are required")
    require_regular_file(unsigned_kit, "personal-team-e2e-kit.json", "unsigned kit manifest")
    require_regular_file(
        overte_ipa, OVERTE_SIGNED_NAME, "signed Overte IPA", private=True
    )
    require_regular_file(
        wda_ipa, WDA_SIGNED_NAME, "signed WebDriverAgent IPA", private=True
    )
    if output.exists() or output.is_symlink():
        raise ValueError("attestation output must be a new path")
    output_parent = require_private_output_parent(output)
    try:
        kit = json.loads(unsigned_kit.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("unsigned kit manifest is invalid") from error
    required = {
        "schemaVersion": 1,
        "contract": KIT_CONTRACT,
        "xcuitestDriverVersion": "12.8.0",
        "webDriverAgentVersion": "16.8.0",
        "webDriverAgentCredentialFreeSigning": WDA_CREDENTIAL_FREE_SIGNING,
        "desiredBundleIdentifiers": EXPECTED_IDS,
    }
    if not isinstance(kit, dict) or any(kit.get(key) != value for key, value in required.items()):
        raise ValueError("unsigned kit manifest contract mismatch")
    reuse = kit.get("overteArtifactReuse")
    if reuse is not None and (
        not isinstance(reuse, dict)
        or reuse.get("contract") != "overte-ios-reusable-e2e-client-v1"
        or reuse.get("sourceRevision") != kit.get("sourceRevision")
        or not isinstance(reuse.get("assemblyRevision"), str)
        or re.fullmatch(r"[0-9a-f]{40}", reuse["assemblyRevision"]) is None
    ):
        raise ValueError("unsigned kit Overte reuse provenance is invalid")
    provenance = kit.get("provenance")
    if (
        not isinstance(provenance, dict)
        or set(provenance) != {
            "repository",
            "repositoryId",
            "workflow",
            "reusableWorkflow",
            "ref",
            "runId",
            "runAttempt",
        }
        or re.fullmatch(
            r"[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}",
            str(provenance.get("repository", "")),
        )
        is None
        or not isinstance(provenance.get("repositoryId"), int)
        or provenance["repositoryId"] <= 0
        or provenance.get("workflow") != ".github/workflows/ios-bootstrap.yml"
        or provenance.get("reusableWorkflow")
        != ".github/workflows/ios-personal-team-e2e-kit.yml"
        or provenance.get("ref") != "refs/heads/apple-ios"
        or not isinstance(provenance.get("runId"), int)
        or provenance["runId"] <= 0
        or not isinstance(provenance.get("runAttempt"), int)
        or provenance["runAttempt"] <= 0
    ):
        raise ValueError("unsigned kit provenance is invalid")
    if kit.get("humanSigningBoundary") != {
        "method": "manual-sideloadly-personal-team",
        "derivationBinding": "human-verified",
        "signedBytesDerivableFromUnsignedKit": False,
        "maximumProfileLifetimeDays": 7,
    }:
        raise ValueError("unsigned kit does not declare the manual re-signing boundary")
    unsigned_artifacts = kit.get("artifacts")
    if not isinstance(unsigned_artifacts, dict):
        raise ValueError("unsigned kit artifact inventory is invalid")
    for kind, name in (
        ("overte", "Overte-PersonalTeam-E2E-unsigned.ipa"),
        ("webDriverAgent", "WebDriverAgentRunner-16.8.0-PersonalTeam-unsigned.ipa"),
    ):
        artifact = unsigned_artifacts.get(kind)
        if (
            not isinstance(artifact, dict)
            or artifact.get("name") != name
            or re.fullmatch(r"[0-9a-f]{64}", str(artifact.get("sha256", ""))) is None
            or not isinstance(artifact.get("size"), int)
            or isinstance(artifact.get("size"), bool)
            or artifact["size"] <= 0
            or artifact["size"] > MAX_IPA_BYTES
        ):
            raise ValueError("unsigned kit artifact inventory is invalid")
    revision = kit.get("sourceRevision")
    if not isinstance(revision, str) or re.fullmatch(r"[0-9a-f]{40}", revision) is None:
        raise ValueError("unsigned kit source revision is invalid")
    created = parse_time(created_at)
    not_after = created + dt.timedelta(days=7)
    payload = {
        "schemaVersion": 1,
        "contract": HANDOFF_CONTRACT,
        "createdAt": created.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "notAfter": not_after.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sourceRevision": revision,
        "unsignedKitManifestSha256": sha256_file(unsigned_kit),
        "xcuitestDriverVersion": "12.8.0",
        "webDriverAgentVersion": "16.8.0",
        "expectedBundleIdentifiers": EXPECTED_IDS,
        "humanAttestation": {
            "derivationBinding": "human-verified",
            "signedFromReviewedUnsignedKit": True,
            "acceptedUnverifiableResigningBoundary": True,
            "samePersonalTeamExpected": True,
        },
        "artifacts": {
            "overte": {
                "name": overte_ipa.name,
                "sha256": sha256_file(overte_ipa),
                "size": overte_ipa.stat().st_size,
            },
            "webDriverAgent": {
                "name": wda_ipa.name,
                "sha256": sha256_file(wda_ipa),
                "size": wda_ipa.stat().st_size,
            },
        },
    }
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(output, flags, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        directory_descriptor = os.open(output_parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except Exception:
        output.unlink(missing_ok=True)
        raise
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--unsigned-kit", type=Path, required=True)
    parser.add_argument("--overte-ipa", type=Path, required=True)
    parser.add_argument("--wda-ipa", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--created-at",
        default=dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
    parser.add_argument("--i-accept-resigning-boundary", action="store_true")
    parser.add_argument("--signed-from-reviewed-kit", action="store_true")
    parser.add_argument("--same-personal-team", action="store_true")
    args = parser.parse_args()
    try:
        create_attestation(
            args.unsigned_kit,
            args.overte_ipa,
            args.wda_ipa,
            args.output,
            args.created_at,
            args.i_accept_resigning_boundary,
            args.signed_from_reviewed_kit,
            args.same_personal_team,
        )
    except (OSError, ValueError) as error:
        print(f"error: Personal Team signed handoff rejected: {error}", file=sys.stderr)
        return 1
    print("PASS private Personal Team signing attestation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
