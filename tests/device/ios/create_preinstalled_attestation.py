#!/usr/bin/env python3
"""Create the short private human attestation for a Sideloadly-preinstalled gate."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys


KIT_CONTRACT = "overte-ios-personal-team-e2e-kit-v2"
ATTESTATION_CONTRACT = "overte-ios-personal-team-preinstalled-attestation-v2"
BUNDLES = {
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
    "signer": "rcodesign", "signerVersion": "0.29.0",
    "signerExecutableSha256":
        "dab9a7465f96aba3c81e793775510f745b91a46b6418e89f7317b5d8fc7bcea2",
}
TOOLCHAIN = {
    "xcuitestDriver": "12.8.0", "remoteXpc": "5.15.3",
    "webdriverAgent": "16.8.0",
}
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
REUSE_CONTRACT = "overte-ios-reusable-e2e-client-v1"


def fail(message: str) -> "NoReturn":
    raise ValueError(message)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def validate_overte_reuse(value: object, source_revision: str) -> None:
    if value is None:
        return
    if not isinstance(value, dict) or set(value) != {
        "schemaVersion", "contract", "assemblyRevision", "sourceRevision",
        "provenance", "artifacts",
    }:
        fail("unsigned kit Overte reuse provenance is invalid")
    provenance = value.get("provenance")
    artifacts = value.get("artifacts")
    if (
        value.get("schemaVersion") != 1
        or value.get("contract") != REUSE_CONTRACT
        or value.get("sourceRevision") != source_revision
        or not isinstance(value.get("assemblyRevision"), str)
        or re.fullmatch(r"[0-9a-f]{40}", value["assemblyRevision"]) is None
        or not isinstance(provenance, dict)
        or set(provenance) != {
            "repository", "repositoryId", "workflow", "ref", "runId",
            "runAttempt", "runNumber", "artifactId", "artifactName",
            "artifactSize", "artifactCreatedAt", "actionsArchiveSha256",
        }
        or provenance.get("repository") != "noah-be/overte"
        or provenance.get("workflow") != ".github/workflows/ios-bootstrap.yml"
        or provenance.get("ref") != "refs/heads/apple-ios"
        or provenance.get("runAttempt") != 1
        or any(not isinstance(provenance.get(key), int)
               or isinstance(provenance[key], bool) or provenance[key] <= 0
               for key in ("repositoryId", "runId", "runNumber", "artifactId",
                           "artifactSize"))
        or provenance.get("artifactName") !=
        f"{provenance.get('runNumber')}-overte-ios-integrated-e2e-unsigned-"
        f"{provenance.get('runId')}"
        or not isinstance(provenance.get("artifactCreatedAt"), str)
        or re.fullmatch(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z",
            provenance["artifactCreatedAt"],
        ) is None
        or not isinstance(provenance.get("actionsArchiveSha256"), str)
        or re.fullmatch(r"[0-9a-f]{64}", provenance["actionsArchiveSha256"]) is None
        or not isinstance(artifacts, dict)
        or set(artifacts) != {"overte", "integratedManifest"}
    ):
        fail("unsigned kit Overte reuse provenance is invalid")
    for metadata in artifacts.values():
        if (not isinstance(metadata, dict)
                or set(metadata) != {"name", "size", "sha256"}
                or not isinstance(metadata.get("name"), str)
                or not isinstance(metadata.get("size"), int)
                or isinstance(metadata["size"], bool) or metadata["size"] <= 0
                or not isinstance(metadata.get("sha256"), str)
                or re.fullmatch(r"[0-9a-f]{64}", metadata["sha256"]) is None):
            fail("unsigned kit Overte reuse inventory is invalid")


def inside_repository(path: Path) -> bool:
    try:
        path.resolve().relative_to(REPOSITORY_ROOT)
        return True
    except ValueError:
        return False


def validate_kit(path: Path, *, private: bool = True) -> dict:
    if (not path.is_absolute() or path.is_symlink() or not path.is_file()
            or inside_repository(path) or not 0 < path.stat().st_size <= 1024 * 1024):
        fail("unsigned kit manifest must be a safe absolute file")
    metadata = path.lstat()
    if (not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.geteuid()
            or metadata.st_nlink != 1 or private and metadata.st_mode & 0o077):
        fail("reviewed unsigned kit manifest must be private mode 0600")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        fail("unsigned kit manifest is unreadable")
    required = {
        "schemaVersion", "contract", "sourceRevision", "createdAt", "provenance",
        "xcuitestDriverVersion", "webDriverAgentVersion", "desiredBundleIdentifiers",
        "webDriverAgentCredentialFreeSigning", "humanSigningBoundary", "upstream",
        "artifacts", "overteArtifactReuse",
    }
    provenance = value.get("provenance") if isinstance(value, dict) else None
    artifacts = value.get("artifacts") if isinstance(value, dict) else None
    upstream = value.get("upstream") if isinstance(value, dict) else None
    if (not isinstance(value, dict) or set(value) != required
            or value.get("schemaVersion") != 1 or value.get("contract") != KIT_CONTRACT
            or not isinstance(value.get("sourceRevision"), str)
            or not re.fullmatch(r"[0-9a-f]{40}", value["sourceRevision"])
            or value.get("xcuitestDriverVersion") != "12.8.0"
            or value.get("webDriverAgentVersion") != "16.8.0"
            or value.get("webDriverAgentCredentialFreeSigning")
            != WDA_CREDENTIAL_FREE_SIGNING
            or value.get("desiredBundleIdentifiers") != BUNDLES
            or value.get("humanSigningBoundary") != {
                "method": "manual-sideloadly-personal-team",
                "derivationBinding": "human-verified",
                "signedBytesDerivableFromUnsignedKit": False,
                "maximumProfileLifetimeDays": 7,
            }
            or upstream != {
                "webDriverAgentUrl": "https://github.com/appium/WebDriverAgent/"
                "releases/download/v16.8.0/WebDriverAgentRunner-Runner.zip",
                "webDriverAgentSha256":
                "38ec705d6fa2c7825513adbc9406d4fda5d6a084a8d3980ceff9a265e62f9623",
            }
            or not isinstance(artifacts, dict)
            or set(artifacts) != {"overte", "webDriverAgent"}
            or not isinstance(provenance, dict) or set(provenance) != {
                "repository", "repositoryId", "workflow", "reusableWorkflow", "ref",
                "runId", "runAttempt"}
            or provenance.get("repository") != "noah-be/overte"
            or provenance.get("workflow") != ".github/workflows/ios-bootstrap.yml"
            or provenance.get("reusableWorkflow")
            != ".github/workflows/ios-personal-team-e2e-kit.yml"
            or provenance.get("ref") != "refs/heads/apple-ios"
            or any(not isinstance(provenance.get(field), int)
                   or isinstance(provenance[field], bool) or provenance[field] <= 0
                   for field in ("repositoryId", "runId", "runAttempt"))):
        fail("unsigned kit manifest contract/provenance is invalid")
    for role, name in {
        "overte": "Overte-PersonalTeam-E2E-unsigned.ipa",
        "webDriverAgent": "WebDriverAgentRunner-16.8.0-PersonalTeam-unsigned.ipa",
    }.items():
        artifact = artifacts[role]
        if (not isinstance(artifact, dict) or set(artifact) != {"name", "sha256", "size"}
                or artifact.get("name") != name
                or not isinstance(artifact.get("sha256"), str)
                or not re.fullmatch(r"[0-9a-f]{64}", artifact["sha256"])
                or not isinstance(artifact.get("size"), int)
                or isinstance(artifact["size"], bool) or artifact["size"] <= 0):
            fail("unsigned kit artifact inventory is invalid")
    validate_overte_reuse(value.get("overteArtifactReuse"), value["sourceRevision"])
    return value


def create(arguments: argparse.Namespace) -> dict:
    fixed_identifiers = arguments.fixed_bundle_identifiers_confirmed
    remapped_identifiers = arguments.accept_sideloadly_bundle_id_remapping
    if (fixed_identifiers == remapped_identifiers
            or not all((arguments.device_observed, arguments.installed_with_sideloadly,
                        arguments.accept_no_cryptographic_byte_binding))):
        fail("all explicit preinstalled human attestations are required")
    kit = validate_kit(arguments.unsigned_kit)
    output = arguments.output
    if (not output.is_absolute() or inside_repository(output) or output.exists()
            or output.is_symlink()):
        fail("private preinstalled attestation must be new and outside the repository")
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    output.parent.chmod(0o700)
    created = datetime.now(timezone.utc).replace(microsecond=0)
    identifier_mode = "fixed" if fixed_identifiers else "sideloadly-remapped"
    human = {
        "deviceObserved": True, "installedWithSideloadly": True,
        "fixedBundleIdentifiersConfirmed": fixed_identifiers,
        "acceptedNoCryptographicByteBinding": True,
        "derivationBinding": "none-device-observed",
    }
    if remapped_identifiers:
        human["acceptedSideloadlyBundleIdentifierRemapping"] = True
    value = {
        "schemaVersion": 1, "contract": ATTESTATION_CONTRACT,
        "sourceRevision": kit["sourceRevision"],
        "createdAt": created.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "notAfter": (created + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "unsignedKitContract": KIT_CONTRACT,
        "unsignedKitManifestSha256": sha256_file(arguments.unsigned_kit),
        "expectedBundleIdentifiers": BUNDLES,
        "bundleIdentifierMode": identifier_mode,
        "toolchain": TOOLCHAIN, "humanAttestation": human,
        "signingObservation": None,
    }
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(output, flags, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        output.unlink(missing_ok=True)
        raise
    return value


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--unsigned-kit", type=Path, required=True)
    value.add_argument("--output", type=Path, required=True)
    value.add_argument("--device-observed", action="store_true")
    value.add_argument("--installed-with-sideloadly", action="store_true")
    value.add_argument("--fixed-bundle-identifiers-confirmed", action="store_true")
    value.add_argument("--accept-sideloadly-bundle-id-remapping", action="store_true")
    value.add_argument("--accept-no-cryptographic-byte-binding", action="store_true")
    return value


def main() -> int:
    try:
        create(parser().parse_args())
        print("PASS: private preinstalled Personal-Team attestation created")
        return 0
    except (ValueError, OSError, KeyError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
