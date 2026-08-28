#!/usr/bin/env python3
"""Verify a private Personal-Team signing handoff without inventing CI provenance."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import plistlib
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile

import verify_fedora_artifacts as VERIFY
import create_preinstalled_attestation as KIT_CONTRACT_VALIDATOR


KIT_CONTRACT = "overte-ios-personal-team-e2e-kit-v3"
ATTESTATION_CONTRACT = "overte-ios-personal-team-signed-handoff-v1"
RECEIPT_CONTRACT = "overte-ios-personal-team-artifact-receipt-v1"
OVERTE_NAME = "Overte-PersonalTeam-E2E-signed.ipa"
WDA_NAME = "WebDriverAgentRunner-16.8.0-PersonalTeam-signed.ipa"
BUNDLES = {
    "overte": "org.overte.interface.e2e",
    "wdaRunner": "org.overte.WebDriverAgentRunner.xctrunner",
    "wdaXCTest": "org.overte.WebDriverAgentRunner",
}
WDA_FRAMEWORK_BUNDLE_ID = "com.facebook.WebDriverAgentLib"
WDA_CREDENTIAL_FREE_SIGNING = {
    "nestedBundle": "PlugIns/WebDriverAgentRunner.xctest",
    "method": "unsigned-requires-recursive-personal-team-signing",
    "outerRunnerBundleCodeResourcesPresent": False,
    "nestedBundleCodeResourcesPresent": False,
    "outerRunnerProvisioned": False,
}
MAX_JSON_BYTES = 1024 * 1024
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def fail(message: str) -> "NoReturn":
    raise VERIFY.VerificationError(message)


def inside_repository(path: Path) -> bool:
    try:
        path.resolve().relative_to(REPOSITORY_ROOT)
        return True
    except ValueError:
        return False


def read_json(path: Path, label: str, *, private: bool = False) -> dict:
    if (VERIFY.has_symlink_component(path) or not path.is_absolute()
            or path.is_symlink() or not path.is_file()
            or private and inside_repository(path)
            or not 0 < path.stat().st_size <= MAX_JSON_BYTES):
        fail(f"{label} must be a safe absolute regular file")
    metadata = path.lstat()
    if (not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1
            or metadata.st_uid != os.geteuid()):
        fail(f"{label} must be an owned singly-linked regular file")
    if private and metadata.st_mode & 0o077:
        fail(f"{label} must have mode 0600")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        fail(f"{label} is unreadable")
    if not isinstance(value, dict):
        fail(f"{label} must be an object")
    return value


def artifact_metadata(value: object, expected_name: str, label: str) -> dict:
    if not isinstance(value, dict) or set(value) != {"name", "sha256", "size"}:
        fail(f"{label} artifact metadata is invalid")
    if (value.get("name") != expected_name
            or not isinstance(value.get("sha256"), str)
            or not VERIFY.SHA256_RE.fullmatch(value["sha256"])
            or isinstance(value.get("size"), bool)
            or not isinstance(value.get("size"), int)
            or not 0 < value["size"] <= VERIFY.MAX_IPA_BYTES):
        fail(f"{label} artifact metadata violates the fixed contract")
    return value


def validate_contracts(arguments: argparse.Namespace) -> tuple[dict, dict, datetime]:
    kit = read_json(arguments.unsigned_kit, "unsigned kit")
    attestation = read_json(arguments.attestation, "signed handoff attestation", private=True)
    kit_keys = {
        "schemaVersion", "contract", "sourceRevision", "createdAt",
        "xcuitestDriverVersion", "webDriverAgentVersion", "artifacts",
        "webDriverAgentCredentialFreeSigning", "desiredBundleIdentifiers",
        "humanSigningBoundary", "upstream", "provenance", "overteArtifactReuse",
    }
    attestation_keys = {
        "schemaVersion", "contract", "createdAt", "notAfter", "sourceRevision",
        "unsignedKitManifestSha256", "humanAttestation", "artifacts",
        "expectedBundleIdentifiers", "xcuitestDriverVersion", "webDriverAgentVersion",
    }
    if set(kit) != kit_keys or kit.get("schemaVersion") != 1 \
            or kit.get("contract") != KIT_CONTRACT:
        fail("unsigned kit contract has unexpected or missing fields")
    if set(attestation) != attestation_keys or attestation.get("schemaVersion") != 1 \
            or attestation.get("contract") != ATTESTATION_CONTRACT:
        fail("signed handoff attestation has unexpected or missing fields")
    if (kit.get("sourceRevision") != attestation.get("sourceRevision")
            or not isinstance(kit.get("sourceRevision"), str)
            or not VERIFY.REVISION_RE.fullmatch(kit["sourceRevision"])):
        fail("Personal-Team source revisions do not match")
    pins = ("12.8.0", "16.8.0")
    if ((kit.get("xcuitestDriverVersion"), kit.get("webDriverAgentVersion")) != pins
            or (attestation.get("xcuitestDriverVersion"),
                attestation.get("webDriverAgentVersion")) != pins):
        fail("Personal-Team handoff differs from the pinned XCUITest/WDA pair")
    if (kit.get("desiredBundleIdentifiers") != BUNDLES
            or attestation.get("expectedBundleIdentifiers") != BUNDLES):
        fail("Personal-Team handoff differs from the fixed non-production bundle IDs")
    if kit.get("webDriverAgentCredentialFreeSigning") != WDA_CREDENTIAL_FREE_SIGNING:
        fail("Personal-Team WDA lacks the recursive XCTest signing boundary")
    try:
        KIT_CONTRACT_VALIDATOR.validate_overte_reuse(
            kit.get("overteArtifactReuse"), kit["sourceRevision"]
        )
    except ValueError as error:
        fail(str(error))
    provenance = kit.get("provenance")
    if (not isinstance(provenance, dict) or set(provenance) != {
            "repository", "repositoryId", "workflow", "reusableWorkflow", "ref",
            "runId", "runAttempt"}
            or provenance.get("repository") != "noah-be/overte"
            or not isinstance(provenance.get("repositoryId"), int)
            or isinstance(provenance.get("repositoryId"), bool)
            or provenance["repositoryId"] <= 0
            or provenance.get("workflow") != ".github/workflows/ios-bootstrap.yml"
            or provenance.get("reusableWorkflow")
            != ".github/workflows/ios-personal-team-e2e-kit.yml"
            or provenance.get("ref") != "refs/heads/apple-ios"
            or any(not isinstance(provenance.get(field), int)
                   or isinstance(provenance[field], bool) or provenance[field] <= 0
                   for field in ("runId", "runAttempt"))):
        fail("unsigned Personal-Team kit provenance is invalid")
    if kit.get("humanSigningBoundary") != {
        "method": "manual-sideloadly-personal-team",
        "derivationBinding": "human-verified",
        "signedBytesDerivableFromUnsignedKit": False,
        "maximumProfileLifetimeDays": 7,
    }:
        fail("unsigned kit does not disclose its human signing boundary")
    if attestation.get("humanAttestation") != {
        "signedFromReviewedUnsignedKit": True,
        "acceptedUnverifiableResigningBoundary": True,
        "samePersonalTeamExpected": True,
        "derivationBinding": "human-verified",
    }:
        fail("private human signing attestation is incomplete")
    if attestation.get("unsignedKitManifestSha256") != VERIFY.sha256_file(
            arguments.unsigned_kit):
        fail("signed handoff attestation does not bind the reviewed unsigned kit")
    upstream = kit.get("upstream")
    if (not isinstance(upstream, dict)
            or set(upstream) != {"webDriverAgentUrl", "webDriverAgentSha256"}
            or upstream.get("webDriverAgentUrl")
            != "https://github.com/appium/WebDriverAgent/releases/download/v16.8.0/"
            "WebDriverAgentRunner-Runner.zip"
            or upstream.get("webDriverAgentSha256")
            != "38ec705d6fa2c7825513adbc9406d4fda5d6a084a8d3980ceff9a265e62f9623"):
        fail("unsigned kit WDA upstream provenance is invalid")
    if not isinstance(kit.get("artifacts"), dict) or set(kit["artifacts"]) != {
            "overte", "webDriverAgent"}:
        fail("unsigned kit artifact set is invalid")
    for role in ("overte", "webDriverAgent"):
        unsigned = kit["artifacts"][role]
        if (not isinstance(unsigned, dict) or set(unsigned) != {"name", "sha256", "size"}
                or not isinstance(unsigned.get("name"), str)
                or Path(unsigned["name"]).name != unsigned["name"]
                or not isinstance(unsigned.get("sha256"), str)
                or not VERIFY.SHA256_RE.fullmatch(unsigned["sha256"])
                or isinstance(unsigned.get("size"), bool)
                or not isinstance(unsigned.get("size"), int) or unsigned["size"] <= 0):
            fail("unsigned kit artifact metadata is invalid")
    if not isinstance(attestation.get("artifacts"), dict) or set(
            attestation["artifacts"]
    ) != {"overte", "webDriverAgent"}:
        fail("signed handoff artifact set is invalid")
    artifact_metadata(attestation["artifacts"]["overte"], OVERTE_NAME, "overte")
    artifact_metadata(attestation["artifacts"]["webDriverAgent"], WDA_NAME, "wda")
    kit_created = VERIFY.parse_utc(kit.get("createdAt"), "unsigned kit createdAt")
    created = VERIFY.parse_utc(attestation.get("createdAt"), "attestation createdAt")
    not_after = VERIFY.parse_utc(attestation.get("notAfter"), "attestation notAfter")
    now = datetime.now(timezone.utc).replace(microsecond=0)
    if (kit_created > created or created > now + VERIFY.MAX_CLOCK_SKEW
            or not_after > created + timedelta(days=7)
            or not_after < now + timedelta(hours=24)):
        fail("Personal-Team attestation validity window is unsafe")
    return kit, attestation, now + timedelta(hours=24)


def validate_signed_input(path: Path, metadata: dict, expected_name: str, label: str) -> None:
    if (path.name != expected_name or not path.is_absolute()
            or VERIFY.has_symlink_component(path) or path.is_symlink() or not path.is_file()
            or inside_repository(path)):
        fail(f"{label} must be the exact private signed IPA export")
    value = path.lstat()
    if (not stat.S_ISREG(value.st_mode) or value.st_uid != os.geteuid()
            or value.st_nlink != 1 or value.st_mode & 0o077):
        fail(f"{label} signed IPA must be owned mode-0600 private data")
    if path.stat().st_size != metadata["size"] or VERIFY.sha256_file(path) != metadata["sha256"]:
        fail(f"{label} signed IPA differs from the human attestation")


def profile_signing(ipa: Path, app_root: str, bundle_id: str, label: str,
                    deadline: datetime) -> dict:
    with zipfile.ZipFile(ipa) as archive, tempfile.TemporaryDirectory(
            prefix="overte-personal-profile-") as name:
        try:
            entry = archive.getinfo(app_root + "embedded.mobileprovision")
        except KeyError:
            fail(f"{label} lacks its embedded provisioning profile")
        profile = Path(name) / "profile.mobileprovision"
        verified = Path(name) / "profile.plist"
        VERIFY.extract_member(archive, entry, profile, VERIFY.MAX_PROFILE_BYTES,
                              f"{label} provisioning profile")
        openssl = shutil.which("openssl")
        if not openssl:
            fail("OpenSSL is required to verify Personal-Team profiles")
        result = subprocess.run(
            [openssl, "cms", "-verify", "-inform", "DER", "-noverify",
             "-in", str(profile), "-out", str(verified)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=30, check=False,
        )
        if result.returncode:
            fail(f"{label} provisioning profile CMS signature is invalid")
        try:
            value = plistlib.loads(verified.read_bytes())
        except (OSError, ValueError, plistlib.InvalidFileException):
            fail(f"{label} verified provisioning profile is invalid")
    teams = value.get("TeamIdentifier") if isinstance(value, dict) else None
    entitlements = value.get("Entitlements") if isinstance(value, dict) else None
    expiry = value.get("ExpirationDate") if isinstance(value, dict) else None
    if (not isinstance(teams, list) or len(teams) != 1
            or not isinstance(teams[0], str) or not VERIFY.TEAM_RE.fullmatch(teams[0])
            or not isinstance(entitlements, dict) or not isinstance(expiry, datetime)):
        fail(f"{label} profile identity is incomplete")
    team = teams[0]
    application_id = f"{team}.{bundle_id}"
    if (entitlements.get("com.apple.developer.team-identifier") not in {None, team}
            or not VERIFY.profile_authorizes(
                entitlements.get("application-identifier"), application_id
            )):
        fail(f"{label} profile does not authorize its fixed bundle ID")
    expiry = expiry.replace(tzinfo=expiry.tzinfo or timezone.utc).astimezone(timezone.utc)
    if expiry < deadline:
        fail(f"{label} Personal-Team profile has less than 24 hours remaining")
    expiration = expiry.strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "signed": True,
        "teamIdentifier": team,
        "applicationIdentifier": application_id,
        "profileExpiration": expiration,
    }


def verify_bundle(ipa: Path, label: str, bundle_id: str, rcodesign: Path,
                  deadline: datetime, *, app_root: str | None = None) -> tuple[dict, str, set[str]]:
    plist, discovered_root, names = VERIFY.archive_plist(ipa, label)
    root = app_root or discovered_root
    if app_root:
        with zipfile.ZipFile(ipa) as archive:
            try:
                plist = plistlib.loads(VERIFY.read_member_limited(
                    archive, archive.getinfo(root + "Info.plist"),
                    VERIFY.MAX_PLIST_BYTES, f"{label} plist",
                ))
            except (KeyError, ValueError, plistlib.InvalidFileException):
                fail(f"{label} plist is invalid")
    if (not isinstance(plist, dict) or plist.get("CFBundleIdentifier") != bundle_id
            or (app_root is None and plist.get("CFBundlePackageType") != "APPL")):
        fail(f"{label} plist differs from its fixed bundle identity")
    if (root + "_CodeSignature/CodeResources" not in names
            or root + "embedded.mobileprovision" not in names):
        fail(f"{label} lacks its signed bundle contract")
    signing = profile_signing(ipa, root, bundle_id, label, deadline)
    manifest = {"notAfter": deadline.strftime("%Y-%m-%dT%H:%M:%SZ"), "signing": signing}
    VERIFY.verify_ipa_signature(
        ipa, label, manifest, plist, root, rcodesign,
        signing=signing, bundle_id=bundle_id,
    )
    return signing, discovered_root, names


def executable_name(plist: dict, label: str) -> str:
    value = plist.get("CFBundleExecutable")
    if (not isinstance(value, str) or not value
            or Path(value).name != value or "/" in value or "\\" in value):
        fail(f"{label} has an invalid executable name")
    return value


def load_signature_info(rcodesign: Path, executable: Path, label: str,
                        temporary: Path) -> object:
    output_path = temporary / "signature-info.yml"
    with output_path.open("xb") as output:
        result = subprocess.run(
            [str(rcodesign), "print-signature-info", "--config-file", "/dev/null",
             str(executable)],
            stdout=output, stderr=subprocess.DEVNULL, timeout=120, check=False,
        )
    output_path.chmod(0o600)
    if (result.returncode or not 0 < output_path.stat().st_size
            <= VERIFY.MAX_SIGNATURE_INFO_BYTES):
        fail(f"{label} signed identity metadata could not be extracted safely")
    try:
        import yaml  # Fedora package: python3-pyyaml; trusted, bounded rcodesign output.
    except ImportError:
        fail("python3-pyyaml is required to attest rcodesign identity metadata")
    try:
        return yaml.safe_load(output_path.read_text(encoding="utf-8"))
    except (yaml.YAMLError, OSError, UnicodeError, ValueError) as error:
        fail(f"{label} signed identity metadata is unreadable: {type(error).__name__}")


def validate_nested_signature_info(value: object, label: str, team: str,
                                   bundle_id: str) -> None:
    if not isinstance(value, list) or len(value) != 1 or not isinstance(value[0], dict):
        fail(f"{label} must contain exactly one signed Mach-O entity")
    try:
        signature = value[0]["entity"]["mach_o"]["signature"]
        code_directory = signature["code_directory"]
        cms = signature["cms"]
    except (KeyError, TypeError):
        fail(f"{label} rcodesign metadata is incomplete")
    if (not isinstance(code_directory, dict)
            or code_directory.get("identifier") != bundle_id
            or code_directory.get("team_name") != team):
        fail(f"{label} code-directory identity differs from the runner")
    if not isinstance(cms, dict):
        fail(f"{label} Mach-O has no cryptographic CMS signature")
    certificates = cms.get("certificates")
    signers = cms.get("signers")
    if (not isinstance(certificates, list) or not isinstance(signers, list)
            or len(signers) != 1 or not isinstance(signers[0], dict)
            or signers[0].get("signature_verifies") is not True):
        fail(f"{label} Mach-O CMS signer could not be cryptographically attested")
    matching = [
        certificate for certificate in certificates
        if isinstance(certificate, dict)
        and certificate.get("apple_team_id") == team
    ]
    if len(matching) != 1:
        fail(f"{label} Mach-O signer team differs from the runner")
    # A non-main XCTest Mach-O must have no entitlement slot at all.  Even an
    # empty plist is still an entitlement slot and is rejected by iOS AMFI.
    if ("entitlements_plist" in signature
            or "entitlements_der_plist" in signature):
        fail(f"{label} unexpectedly contains an entitlement slot")


def verified_leaf_signer(rcodesign: Path, executable: Path, label: str,
                         temporary: Path) -> bytes:
    openssl = shutil.which("openssl")
    if not openssl:
        fail("OpenSSL is required to verify the Mach-O signer")
    cms_path = temporary / "macho-signature.pem"
    directory_path = temporary / "macho-code-directory.bin"
    signer_path = temporary / "macho-signer.pem"
    signer_der = temporary / "macho-signer.der"
    with cms_path.open("xb") as output:
        cms = subprocess.run(
            [str(rcodesign), "extract", "--config-file", "/dev/null", "cms-pem",
             str(executable)],
            stdout=output, stderr=subprocess.DEVNULL, timeout=60, check=False,
        )
    cms_path.chmod(0o600)
    with directory_path.open("xb") as output:
        directory = subprocess.run(
            [str(rcodesign), "extract", "--config-file", "/dev/null",
             "code-directory-raw", str(executable)],
            stdout=output, stderr=subprocess.DEVNULL, timeout=60, check=False,
        )
    directory_path.chmod(0o600)
    if (cms.returncode or directory.returncode
            or not 0 < cms_path.stat().st_size <= VERIFY.MAX_SIGNATURE_INFO_BYTES
            or not 0 < directory_path.stat().st_size <= VERIFY.MAX_SIGNATURE_INFO_BYTES):
        fail(f"{label} Mach-O signer material could not be extracted safely")
    verification = subprocess.run(
        [openssl, "cms", "-verify", "-inform", "PEM", "-noverify",
         "-in", str(cms_path), "-binary", "-content", str(directory_path),
         "-out", "/dev/null", "-signer", str(signer_path)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30, check=False,
    )
    conversion = subprocess.run(
        [openssl, "x509", "-in", str(signer_path), "-outform", "DER",
         "-out", str(signer_der)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15, check=False,
    ) if verification.returncode == 0 and signer_path.is_file() else None
    if (verification.returncode or conversion is None or conversion.returncode
            or not signer_der.is_file()
            or not 0 < signer_der.stat().st_size <= VERIFY.MAX_SIGNATURE_INFO_BYTES):
        fail(f"{label} Mach-O CMS signer certificate is invalid")
    return signer_der.read_bytes()


def bundle_leaf_signer(ipa: Path, root: str, plist: dict, rcodesign: Path,
                       label: str) -> bytes:
    executable = executable_name(plist, label)
    with zipfile.ZipFile(ipa) as archive, tempfile.TemporaryDirectory(
            prefix="overte-personal-leaf-") as name:
        try:
            info = archive.getinfo(root + executable)
        except KeyError:
            fail(f"{label} lacks its signed executable")
        temporary = Path(name)
        extracted = temporary / "main"
        VERIFY.extract_member(
            archive, info, extracted, VERIFY.MAX_EXECUTABLE_BYTES, f"{label} executable"
        )
        extracted.chmod(0o700)
        return verified_leaf_signer(rcodesign, extracted, label, temporary)


def verify_nested_code_bundle(ipa: Path, root: str, names: set[str],
                              bundle_id: str, package_type: str, label: str,
                              runner_team: str, runner_leaf: bytes,
                              rcodesign: Path) -> None:
    info_name = root + "Info.plist"
    resources_name = root + "_CodeSignature/CodeResources"
    if info_name not in names or resources_name not in names:
        fail(f"Personal-Team WDA lacks the signed nested {label} bundle")
    profiles = {
        root + "embedded.mobileprovision",
        root + "embedded.provisionprofile",
    }
    if names & profiles:
        fail(f"Personal-Team WDA nested {label} must not contain a provisioning profile")
    with zipfile.ZipFile(ipa) as archive, tempfile.TemporaryDirectory(
            prefix="overte-personal-nested-") as name:
        try:
            plist = plistlib.loads(VERIFY.read_member_limited(
                archive, archive.getinfo(info_name), VERIFY.MAX_PLIST_BYTES,
                f"webdriveragent {label} plist",
            ))
        except (KeyError, ValueError, plistlib.InvalidFileException):
            fail(f"webdriveragent {label} plist is invalid")
        if (not isinstance(plist, dict)
                or plist.get("CFBundleIdentifier") != bundle_id
                or plist.get("CFBundlePackageType") != package_type):
            fail(f"webdriveragent {label} plist differs from its fixed bundle identity")
        executable = executable_name(plist, f"webdriveragent {label}")
        try:
            executable_info = archive.getinfo(root + executable)
        except KeyError:
            fail(f"webdriveragent {label} lacks its signed executable")
        temporary = Path(name)
        extracted = temporary / "main"
        VERIFY.extract_member(
            archive, executable_info, extracted, VERIFY.MAX_EXECUTABLE_BYTES,
            f"webdriveragent {label} executable",
        )
        extracted.chmod(0o700)
        signature = subprocess.run(
            [str(rcodesign), "verify", "--config-file", "/dev/null", str(extracted)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=120, check=False,
        )
        if signature.returncode:
            fail(f"webdriveragent {label} Mach-O code signature failed verification")
        validate_nested_signature_info(
            load_signature_info(
                rcodesign, extracted, f"webdriveragent {label}", temporary
            ),
            f"webdriveragent {label}", runner_team, bundle_id,
        )
        nested_leaf = verified_leaf_signer(
            rcodesign, extracted, f"webdriveragent {label}", temporary
        )
        if nested_leaf != runner_leaf:
            fail(f"WDA Runner and nested {label} have different leaf signers")


def verify_nested_xctest(ipa: Path, root: str, names: set[str], bundle_id: str,
                         runner_team: str, runner_leaf: bytes,
                         rcodesign: Path) -> None:
    verify_nested_code_bundle(
        ipa, root, names, bundle_id, "BNDL", "XCTest",
        runner_team, runner_leaf, rcodesign,
    )


def verify_nested_framework(ipa: Path, root: str, names: set[str],
                            runner_team: str, runner_leaf: bytes,
                            rcodesign: Path) -> None:
    verify_nested_code_bundle(
        ipa, root, names, WDA_FRAMEWORK_BUNDLE_ID, "FMWK", "framework",
        runner_team, runner_leaf, rcodesign,
    )


def run(arguments: argparse.Namespace) -> int:
    if inside_repository(arguments.receipt):
        fail("Personal-Team receipt must remain outside the repository")
    _kit, attestation, deadline = validate_contracts(arguments)
    validate_signed_input(
        arguments.overte_ipa, attestation["artifacts"]["overte"], OVERTE_NAME, "overte"
    )
    validate_signed_input(
        arguments.wda_ipa, attestation["artifacts"]["webDriverAgent"], WDA_NAME, "wda"
    )
    lock = json.loads(VERIFY.LOCK_FILE.read_text(encoding="utf-8"))
    rcodesign = VERIFY.validate_rcodesign(arguments.rcodesign, lock)
    overte_signing, _overte_root, _ = verify_bundle(
        arguments.overte_ipa, "overte-app", BUNDLES["overte"], rcodesign, deadline
    )
    overte_plist, _, _ = VERIFY.archive_plist(arguments.overte_ipa, "overte-app")
    if (overte_plist.get("OverteE2ETestBuildContractVersion") != 1
            or overte_plist.get("UIFileSharingEnabled") is not True):
        fail("Personal-Team Overte IPA lacks E2E contract version 1")
    wda_signing, wda_root, wda_names = verify_bundle(
        arguments.wda_ipa, "webdriveragent", BUNDLES["wdaRunner"], rcodesign, deadline
    )
    wda_plist, _, _ = VERIFY.archive_plist(arguments.wda_ipa, "webdriveragent")
    if (wda_plist.get("OverteE2EWebDriverAgentVersion") != "16.8.0"
            or wda_plist.get("OverteE2EXCUITestDriverVersion") != "12.8.0"):
        fail("Personal-Team WDA IPA lacks its exact XCUITest/WDA pairing markers")
    nested_root = wda_root + "PlugIns/WebDriverAgentRunner.xctest/"
    if overte_signing["teamIdentifier"] != wda_signing["teamIdentifier"]:
        fail("Overte and WDA Runner are not signed by the same Personal Team")
    runner_leaf = bundle_leaf_signer(
        arguments.wda_ipa, wda_root, wda_plist, rcodesign, "webdriveragent"
    )
    verify_nested_xctest(
        arguments.wda_ipa, nested_root, wda_names, BUNDLES["wdaXCTest"],
        wda_signing["teamIdentifier"], runner_leaf, rcodesign,
    )
    framework_root = nested_root + "Frameworks/WebDriverAgentLib.framework/"
    verify_nested_framework(
        arguments.wda_ipa, framework_root, wda_names,
        wda_signing["teamIdentifier"], runner_leaf, rcodesign,
    )
    prebuilt_path, prebuilt_digest = VERIFY.extract_prebuilt_wda(
        arguments.wda_ipa, arguments.receipt.parent / VERIFY.PREBUILT_WDA_NAME
    )
    created = datetime.now(timezone.utc).replace(microsecond=0)
    provenance = {
        "mode": "personal-team-manual-signing",
        "unsignedKitContract": KIT_CONTRACT,
        "unsignedKitManifestSha256": VERIFY.sha256_file(arguments.unsigned_kit),
        "attestationContract": ATTESTATION_CONTRACT,
        "derivationBinding": "human-verified",
    }
    receipt = {
        "schemaVersion": 1,
        "contract": RECEIPT_CONTRACT,
        "sourceRevision": attestation["sourceRevision"],
        "createdAt": created.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "notAfter": deadline.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "provenance": provenance,
        "overte": {
            "path": str(arguments.overte_ipa.resolve()),
            "sha256": VERIFY.sha256_file(arguments.overte_ipa),
            "bundleId": BUNDLES["overte"],
        },
        "wda": {
            "ipaPath": str(arguments.wda_ipa.resolve()),
            "ipaSha256": VERIFY.sha256_file(arguments.wda_ipa),
            "prebuiltPath": str(prebuilt_path),
            "prebuiltTreeSha256": prebuilt_digest,
            "bundleId": BUNDLES["wdaRunner"],
        },
        "toolchain": {
            "xcuitestDriver": "12.8.0",
            "remoteXpc": "5.15.3",
            "webdriverAgent": "16.8.0",
        },
    }
    try:
        VERIFY.secure_write(arguments.receipt, receipt)
    except BaseException:
        shutil.rmtree(prebuilt_path, ignore_errors=True)
        raise
    print("PASS: verified private Personal-Team iOS handoff")
    return 0


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--unsigned-kit", type=Path, required=True)
    value.add_argument("--attestation", type=Path, required=True)
    value.add_argument("--overte-ipa", type=Path, required=True)
    value.add_argument("--wda-ipa", type=Path, required=True)
    value.add_argument("--receipt", type=Path, required=True)
    value.add_argument("--rcodesign", type=Path, required=True)
    return value


def main() -> int:
    try:
        return run(parser().parse_args())
    except (VERIFY.VerificationError, OSError, KeyError, json.JSONDecodeError,
            subprocess.SubprocessError, zipfile.BadZipFile) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
