#!/usr/bin/env python3
"""Verify signed iOS E2E/WDA handoff artifacts and write a private Fedora receipt."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import plistlib
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unicodedata
import zipfile


IOS_ROOT = Path(__file__).resolve().parent
if str(IOS_ROOT) not in sys.path:
    sys.path.insert(0, str(IOS_ROOT))
from private_artifact_tree import (  # noqa: E402
    ArtifactTreeError,
    tree_sha256 as canonical_tree_sha256,
)


LOCK_FILE = Path(__file__).with_name("toolchain.lock.json")
ARTIFACT_CONTRACT = "overte-ios-fedora-e2e-artifact-v1"
RECEIPT_CONTRACT = "overte-ios-fedora-e2e-receipt-v1"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
REVISION_RE = re.compile(r"^[0-9a-f]{40}$")
BUNDLE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]*(?:\.[A-Za-z0-9][A-Za-z0-9-]*)+$")
REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
TEAM_RE = re.compile(r"^[A-Z0-9]{10}$")
RFC3339_SECONDS_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")
PRODUCER_WORKFLOW = ".github/workflows/ios-bootstrap.yml"
REUSABLE_PRODUCER_WORKFLOW = ".github/workflows/ios-fedora-e2e-producer.yml"
PRODUCER_REF = "refs/heads/apple-ios"
MAX_ARCHIVE_ENTRIES = 200_000
MAX_IPA_BYTES = 4 * 1024 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 16 * 1024 * 1024 * 1024
MAX_PLIST_BYTES = 4 * 1024 * 1024
MAX_EXECUTABLE_BYTES = 768 * 1024 * 1024
MAX_PROFILE_BYTES = 8 * 1024 * 1024
MAX_SIGNATURE_INFO_BYTES = 16 * 1024 * 1024
MAX_CLOCK_SKEW = timedelta(minutes=5)
PREBUILT_WDA_NAME = "WebDriverAgentRunner-Runner.app"
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


class VerificationError(ValueError):
    """A producer artifact does not satisfy the Fedora handoff contract."""


def fail(message: str) -> "NoReturn":
    raise VerificationError(message)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_utc(value: object, label: str) -> datetime:
    if not isinstance(value, str) or not RFC3339_SECONDS_RE.fullmatch(value):
        fail(f"{label} must be RFC3339 UTC with whole seconds")
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        fail(f"{label} is not a real timestamp")


def validate_provenance(value: object, kind: str) -> dict:
    expected = {
        "repository", "repositoryId", "workflow", "reusableWorkflow", "ref",
        "runId", "runAttempt",
    }
    if not isinstance(value, dict) or set(value) != expected:
        fail(f"{kind} provenance has unexpected or missing fields")
    if not isinstance(value["repository"], str) or not REPOSITORY_RE.fullmatch(
        value["repository"]
    ):
        fail(f"{kind} provenance repository is invalid")
    if (value["workflow"] != PRODUCER_WORKFLOW
            or value["reusableWorkflow"] != REUSABLE_PRODUCER_WORKFLOW
            or value["ref"] != PRODUCER_REF):
        fail(f"{kind} provenance is outside the protected producer")
    for field in ("repositoryId", "runId", "runAttempt"):
        if isinstance(value[field], bool) or not isinstance(value[field], int) or value[field] <= 0:
            fail(f"{kind} provenance {field} must be a positive integer")
    return value


def load_manifest(path: Path, kind: str, *, now: datetime | None = None) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        fail(f"{kind} manifest is unreadable: {type(error).__name__}")
    if not isinstance(value, dict):
        fail(f"{kind} manifest must be an object")
    common = {
        "schemaVersion", "contract", "kind", "sourceRevision", "createdAt", "notAfter",
        "provenance", "artifact", "bundle", "signing",
    }
    expected = common | (
        {"testBuildContractVersion"} if kind == "overte-app" else {"toolchain", "xctest"}
    )
    if set(value) != expected:
        fail(f"{kind} manifest has unexpected or missing fields")
    if value.get("schemaVersion") != 1 or value.get("contract") != ARTIFACT_CONTRACT:
        fail(f"{kind} manifest contract is unsupported")
    if value.get("kind") != kind:
        fail(f"{kind} manifest kind does not match its role")
    if not isinstance(value.get("sourceRevision"), str) or not REVISION_RE.fullmatch(
        value["sourceRevision"]
    ):
        fail(f"{kind} sourceRevision must be an exact Git revision")
    created = parse_utc(value.get("createdAt"), f"{kind} createdAt")
    not_after = parse_utc(value.get("notAfter"), f"{kind} notAfter")
    if not_after != created + timedelta(hours=24):
        fail(f"{kind} notAfter must be exactly 24 hours after createdAt")
    current = now or datetime.now(timezone.utc)
    if created > current + MAX_CLOCK_SKEW:
        fail(f"{kind} createdAt is implausibly in the future")
    if not_after <= current:
        fail(f"{kind} handoff validity window has expired")
    validate_provenance(value.get("provenance"), kind)
    forbidden = {"udid", "deviceudid", "provisioneddevices", "deviceidentifiers"}
    stack = [value]
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            if any(str(key).lower() in forbidden for key in item):
                fail(f"{kind} manifest must not disclose device identifiers")
            stack.extend(item.values())
        elif isinstance(item, list):
            stack.extend(item)
    return value


def validate_signing_metadata(value: object, bundle_id: str, kind: str,
                              not_after: datetime) -> dict:
    signing = value
    if not isinstance(signing, dict) or set(signing) != {
        "signed", "teamIdentifier", "applicationIdentifier", "profileExpiration"
    }:
        fail(f"{kind} signing metadata is invalid")
    team = signing.get("teamIdentifier")
    if signing.get("signed") is not True or not isinstance(team, str) or not TEAM_RE.fullmatch(team):
        fail(f"{kind} must be signed by an exact development team identifier")
    if signing.get("applicationIdentifier") != f"{team}.{bundle_id}":
        fail(f"{kind} application identifier does not match team and bundle")
    expiry = parse_utc(signing.get("profileExpiration"), f"{kind} profile expiration")
    if expiry < not_after:
        fail(f"{kind} provisioning profile expires before the handoff validity window")
    return signing


def validate_metadata(manifest: dict, artifact_path: Path, kind: str) -> tuple[str, str]:
    artifact = manifest.get("artifact")
    if not isinstance(artifact, dict) or set(artifact) != {"name", "sha256", "size"}:
        fail(f"{kind} artifact metadata is invalid")
    if artifact.get("name") != artifact_path.name:
        fail(f"{kind} artifact name does not match the selected file")
    if not isinstance(artifact.get("size"), int) or artifact["size"] <= 0:
        fail(f"{kind} artifact size is invalid")
    if not isinstance(artifact.get("sha256"), str) or not SHA256_RE.fullmatch(
        artifact["sha256"]
    ):
        fail(f"{kind} artifact SHA-256 is invalid")
    if (artifact_path.is_symlink() or not artifact_path.is_file()
            or artifact_path.stat().st_size != artifact["size"]):
        fail(f"{kind} artifact bytes do not match the manifest size")
    if artifact["size"] > MAX_IPA_BYTES:
        fail(f"{kind} artifact exceeds the Fedora IPA size limit")
    actual_sha = sha256_file(artifact_path)
    if actual_sha != artifact["sha256"]:
        fail(f"{kind} artifact failed its SHA-256")

    bundle = manifest.get("bundle")
    if not isinstance(bundle, dict) or set(bundle) != {"id"}:
        fail(f"{kind} bundle metadata is invalid")
    bundle_id = bundle.get("id")
    if not isinstance(bundle_id, str) or not BUNDLE_RE.fullmatch(bundle_id):
        fail(f"{kind} bundle identifier is invalid")

    validate_signing_metadata(
        manifest.get("signing"), bundle_id, kind,
        parse_utc(manifest["notAfter"], f"{kind} notAfter"),
    )
    return bundle_id, actual_sha


def read_member_limited(archive: zipfile.ZipFile, info: zipfile.ZipInfo,
                        limit: int, label: str) -> bytes:
    if info.file_size <= 0 or info.file_size > limit:
        fail(f"{label} size is invalid")
    chunks: list[bytes] = []
    total = 0
    with archive.open(info) as source:
        while block := source.read(min(1024 * 1024, limit - total + 1)):
            total += len(block)
            if total > limit:
                fail(f"{label} exceeded its extraction limit")
            chunks.append(block)
    if total != info.file_size:
        fail(f"{label} extracted size does not match its ZIP metadata")
    return b"".join(chunks)


def archive_plist(artifact_path: Path, kind: str) -> tuple[dict, str, set[str]]:
    try:
        archive = zipfile.ZipFile(artifact_path)
    except (OSError, zipfile.BadZipFile):
        fail(f"{kind} artifact is not a valid IPA ZIP archive")
    with archive:
        entries = archive.infolist()
        if not entries or len(entries) > MAX_ARCHIVE_ENTRIES:
            fail(f"{kind} IPA entry count is invalid")
        total_uncompressed = sum(entry.file_size for entry in entries)
        total_compressed = sum(max(1, entry.compress_size) for entry in entries)
        if total_uncompressed > MAX_UNCOMPRESSED_BYTES:
            fail(f"{kind} IPA expands beyond the safety limit")
        if total_uncompressed > total_compressed * 500:
            fail(f"{kind} IPA compression ratio exceeds the safety limit")
        names: set[str] = set()
        portable_names: set[str] = set()
        for entry in entries:
            name = entry.filename
            path = PurePosixPath(name)
            if (not name or path.is_absolute() or "\\" in name
                    or any(part in {"", ".", ".."} for part in path.parts)
                    or entry.flag_bits & 0x1):
                fail(f"{kind} IPA contains an unsafe entry")
            mode = (entry.external_attr >> 16) & 0o170000
            if mode not in {0, stat.S_IFREG, stat.S_IFDIR}:
                fail(f"{kind} IPA contains a link or special file")
            normalized = name.rstrip("/")
            portable = unicodedata.normalize("NFC", normalized).casefold()
            if normalized in names or portable in portable_names:
                fail(f"{kind} IPA contains duplicate entries")
            names.add(normalized)
            portable_names.add(portable)
        plist_names = [
            name for name in names
            if re.fullmatch(r"Payload/[^/]+[.]app/Info[.]plist", name)
        ]
        if len(plist_names) != 1:
            fail(f"{kind} IPA must contain exactly one top-level application plist")
        plist_name = plist_names[0]
        info = archive.getinfo(plist_name)
        try:
            plist = plistlib.loads(read_member_limited(
                archive, info, MAX_PLIST_BYTES, f"{kind} application plist"
            ))
        except (ValueError, plistlib.InvalidFileException):
            fail(f"{kind} application plist is invalid")
        if not isinstance(plist, dict):
            fail(f"{kind} application plist must be a dictionary")
        return plist, plist_name.removesuffix("Info.plist"), names


def validate_rcodesign(path: Path, lock: dict) -> Path:
    entry = lock["appium"]["iosSecurity"]["rcodesign"]
    if path.is_symlink() or not path.is_absolute() or not path.is_file():
        fail("rcodesign must be an absolute pinned executable")
    if sha256_file(path) != entry["executableSha256"]:
        fail("rcodesign executable failed its pinned SHA-256")
    result = subprocess.run(
        [str(path), "--version"], text=True, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, timeout=15, check=False,
    )
    if result.returncode or result.stdout.strip() != f"apple-codesign {entry['version']}":
        fail("rcodesign executable failed its exact version pin")
    return path


def profile_authorizes(profile_id: object, application_id: str) -> bool:
    if not isinstance(profile_id, str) or not profile_id:
        return False
    if "*" not in profile_id:
        return profile_id == application_id
    prefix = profile_id[:-1]
    team_prefix = application_id.partition(".")[0] + "."
    return profile_id.count("*") == 1 and profile_id.endswith("*") \
        and prefix != team_prefix and application_id.startswith(prefix)


def extract_member(archive: zipfile.ZipFile, info: zipfile.ZipInfo, destination: Path,
                   limit: int, label: str) -> None:
    if info.file_size <= 0 or info.file_size > limit:
        fail(f"{label} size is invalid")
    total = 0
    with archive.open(info) as source, destination.open("xb") as output:
        while block := source.read(min(1024 * 1024, limit - total + 1)):
            total += len(block)
            if total > limit:
                fail(f"{label} exceeded its extraction limit")
            output.write(block)
        output.flush()
        os.fsync(output.fileno())
    if total != info.file_size:
        fail(f"{label} extracted size does not match its ZIP metadata")
    destination.chmod(0o600)


def signed_entitlements(rcodesign: Path, executable: Path, kind: str,
                        signing: dict, bundle_id: str, temporary: Path) -> dict:
    """Bind the Mach-O CMS signer, identifier, and entitlements to the manifest."""
    output_path = temporary / "signature-info.yml"
    with output_path.open("xb") as output:
        result = subprocess.run(
            [str(rcodesign), "print-signature-info", "--config-file", "/dev/null",
             str(executable)],
            stdout=output, stderr=subprocess.DEVNULL, timeout=120, check=False,
        )
    output_path.chmod(0o600)
    if result.returncode or output_path.stat().st_size > MAX_SIGNATURE_INFO_BYTES:
        fail(f"{kind} signed identity metadata could not be extracted safely")
    try:
        import yaml  # Fedora package: python3-pyyaml; only trusted, bounded rcodesign output.
    except ImportError:
        fail("python3-pyyaml is required to attest rcodesign identity metadata")
    try:
        value = yaml.safe_load(output_path.read_text(encoding="utf-8"))
    except (yaml.YAMLError, OSError, UnicodeError, ValueError) as error:
        fail(f"{kind} signed identity metadata is unreadable: {type(error).__name__}")
    return validate_signature_info(value, kind, signing, bundle_id)


def validate_signature_info(value: object, kind: str, signing: dict,
                            bundle_id: str) -> dict:
    if not isinstance(value, list) or len(value) != 1 or not isinstance(value[0], dict):
        fail(f"{kind} must contain exactly one signed Mach-O entity")
    try:
        signature = value[0]["entity"]["mach_o"]["signature"]
        code_directory = signature["code_directory"]
        cms = signature["cms"]
    except (KeyError, TypeError):
        fail(f"{kind} rcodesign metadata is incomplete")
    if not isinstance(code_directory, dict) or code_directory.get("identifier") != bundle_id:
        fail(f"{kind} signed code-directory identifier differs from its bundle")
    if not isinstance(cms, dict):
        fail(f"{kind} Mach-O has no cryptographic CMS signature")
    certificates = cms.get("certificates")
    signers = cms.get("signers")
    if (not isinstance(certificates, list) or not isinstance(signers, list)
            or len(signers) != 1 or signers[0].get("signature_verifies") is not True):
        fail(f"{kind} Mach-O CMS signer could not be cryptographically attested")
    matching_teams = [
        certificate for certificate in certificates
        if isinstance(certificate, dict)
        and certificate.get("apple_team_id") == signing["teamIdentifier"]
        and certificate.get("apple_certificate_profile")
        in {"apple-development", "apple-distribution"}
    ]
    if len(matching_teams) != 1:
        fail(f"{kind} Mach-O signer team differs from the manifest/profile")
    xml_lines = signature.get("entitlements_plist")
    der_lines = signature.get("entitlements_der_plist")
    if not isinstance(xml_lines, list) or not all(isinstance(line, str) for line in xml_lines):
        fail(f"{kind} signed XML entitlements are unavailable")
    try:
        entitlements = plistlib.loads(("\n".join(xml_lines) + "\n").encode("utf-8"))
    except (ValueError, plistlib.InvalidFileException):
        fail(f"{kind} signed XML entitlements are invalid")
    if isinstance(der_lines, list) and all(isinstance(line, str) for line in der_lines):
        try:
            der_entitlements = plistlib.loads(("\n".join(der_lines) + "\n").encode("utf-8"))
        except (ValueError, plistlib.InvalidFileException):
            fail(f"{kind} signed DER entitlements are invalid")
        if der_entitlements != entitlements:
            fail(f"{kind} signed XML and DER entitlements disagree")
    if (not isinstance(entitlements, dict)
            or entitlements.get("application-identifier") != signing["applicationIdentifier"]
            or entitlements.get("com.apple.developer.team-identifier")
            != signing["teamIdentifier"]):
        fail(f"{kind} signed entitlements differ from manifest/profile identity")
    return entitlements


def verify_leaf_profile_membership(rcodesign: Path, openssl: str, executable: Path,
                                   profile: dict, not_after: datetime, kind: str,
                                   temporary: Path) -> None:
    cms_path = temporary / "macho-signature.pem"
    code_directory_path = temporary / "macho-code-directory.bin"
    signer_path = temporary / "macho-signer.pem"
    signer_der = temporary / "macho-signer.der"
    with cms_path.open("xb") as output:
        extraction = subprocess.run(
            [str(rcodesign), "extract", "--config-file", "/dev/null", "cms-pem",
             str(executable)],
            stdout=output, stderr=subprocess.DEVNULL, timeout=60, check=False,
        )
    cms_path.chmod(0o600)
    if (extraction.returncode or not 0 < cms_path.stat().st_size <= MAX_SIGNATURE_INFO_BYTES):
        fail(f"{kind} Mach-O signer certificate could not be extracted")
    with code_directory_path.open("xb") as output:
        code_directory = subprocess.run(
            [str(rcodesign), "extract", "--config-file", "/dev/null",
             "code-directory-raw", str(executable)],
            stdout=output, stderr=subprocess.DEVNULL, timeout=60, check=False,
        )
    code_directory_path.chmod(0o600)
    if (code_directory.returncode
            or not 0 < code_directory_path.stat().st_size <= MAX_SIGNATURE_INFO_BYTES):
        fail(f"{kind} signed code directory could not be extracted")
    verification = subprocess.run(
        [openssl, "cms", "-verify", "-inform", "PEM", "-noverify", "-in", str(cms_path),
         "-binary", "-content", str(code_directory_path),
         "-out", "/dev/null", "-signer", str(signer_path)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30, check=False,
    )
    if verification.returncode or not signer_path.is_file():
        fail(f"{kind} Mach-O CMS signer certificate is invalid")
    conversion = subprocess.run(
        [openssl, "x509", "-in", str(signer_path), "-outform", "DER", "-out", str(signer_der)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15, check=False,
    )
    if conversion.returncode or not signer_der.is_file():
        fail(f"{kind} Mach-O signer certificate is unreadable")
    developer_certificates = profile.get("DeveloperCertificates")
    if (not isinstance(developer_certificates, list)
            or signer_der.read_bytes() not in developer_certificates):
        fail(f"{kind} Mach-O signer is not authorized by the provisioning profile")
    remaining = max(0, int((not_after - datetime.now(timezone.utc)).total_seconds()))
    validity = subprocess.run(
        [openssl, "x509", "-in", str(signer_path), "-noout", "-checkend", str(remaining)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15, check=False,
    )
    if validity.returncode:
        fail(f"{kind} Mach-O signer expires before the handoff validity window")


def verify_ipa_signature(artifact_path: Path, kind: str, manifest: dict, plist: dict,
                         app_root: str, rcodesign: Path, *, signing: dict | None = None,
                         bundle_id: str | None = None) -> None:
    executable_name = plist.get("CFBundleExecutable")
    if (
        not isinstance(executable_name, str) or not executable_name
        or PurePosixPath(executable_name).name != executable_name
    ):
        fail(f"{kind} IPA has an invalid main executable name")
    executable_entry = f"{app_root}{executable_name}"
    profile_entry = f"{app_root}embedded.mobileprovision"
    with zipfile.ZipFile(artifact_path) as archive:
        try:
            executable_info = archive.getinfo(executable_entry)
            profile_info = archive.getinfo(profile_entry)
        except KeyError:
            fail(f"{kind} IPA lacks executable or provisioning profile bytes")
        if not 0 < executable_info.file_size <= MAX_EXECUTABLE_BYTES:
            fail(f"{kind} main executable size is invalid")
        if not 0 < profile_info.file_size <= MAX_PROFILE_BYTES:
            fail(f"{kind} provisioning profile size is invalid")
        with tempfile.TemporaryDirectory(prefix="overte-ios-signature-") as name:
            temporary = Path(name)
            executable = temporary / "main"
            profile = temporary / "profile.mobileprovision"
            verified_profile = temporary / "profile.plist"
            extract_member(
                archive, executable_info, executable, MAX_EXECUTABLE_BYTES,
                f"{kind} main executable",
            )
            extract_member(
                archive, profile_info, profile, MAX_PROFILE_BYTES,
                f"{kind} provisioning profile",
            )
            executable.chmod(0o700)
            signature = subprocess.run(
                [str(rcodesign), "verify", "--config-file", "/dev/null", str(executable)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=120, check=False,
            )
            if signature.returncode:
                fail(f"{kind} Mach-O code signature failed cryptographic verification")
            expected_signing = signing or manifest["signing"]
            expected_bundle = bundle_id or manifest["bundle"]["id"]
            signed_entitlements(
                rcodesign, executable, kind, expected_signing, expected_bundle, temporary
            )
            openssl = shutil.which("openssl")
            if not openssl:
                fail("OpenSSL is required to verify the provisioning profile CMS")
            cms = subprocess.run(
                [openssl, "cms", "-verify", "-inform", "DER", "-noverify",
                 "-in", str(profile), "-out", str(verified_profile)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=30, check=False,
            )
            if cms.returncode:
                fail(f"{kind} provisioning profile CMS signature is invalid")
            try:
                profile_plist = plistlib.loads(verified_profile.read_bytes())
            except (OSError, plistlib.InvalidFileException, ValueError):
                fail(f"{kind} verified provisioning profile is not a plist")
            verify_leaf_profile_membership(
                rcodesign, openssl, executable, profile_plist,
                parse_utc(manifest["notAfter"], f"{kind} notAfter"), kind, temporary,
            )

    signing = signing or manifest["signing"]
    team = signing["teamIdentifier"]
    teams = profile_plist.get("TeamIdentifier")
    entitlements = profile_plist.get("Entitlements")
    expiration = profile_plist.get("ExpirationDate")
    if teams != [team] or not isinstance(entitlements, dict):
        fail(f"{kind} provisioning profile does not identify the manifest team")
    if entitlements.get("com.apple.developer.team-identifier") not in {None, team}:
        fail(f"{kind} provisioning profile entitlement has a different team")
    if not profile_authorizes(
        entitlements.get("application-identifier"), signing["applicationIdentifier"]
    ):
        fail(f"{kind} provisioning profile does not authorize the signed application")
    if not isinstance(expiration, datetime):
        fail(f"{kind} provisioning profile has no expiration date")
    profile_expiry = expiration.replace(tzinfo=expiration.tzinfo or timezone.utc)
    manifest_expiry = parse_utc(signing["profileExpiration"], f"{kind} profile expiration")
    if profile_expiry.astimezone(timezone.utc) != manifest_expiry.astimezone(timezone.utc):
        fail(f"{kind} manifest profile expiration does not match signed CMS content")


def verify_one(manifest_path: Path, artifact_path: Path, kind: str, lock: dict,
               rcodesign: Path) -> dict:
    manifest = load_manifest(manifest_path, kind)
    bundle_id, digest = validate_metadata(manifest, artifact_path, kind)
    plist, app_root, names = archive_plist(artifact_path, kind)
    if plist.get("CFBundleIdentifier") != bundle_id or plist.get("CFBundlePackageType") != "APPL":
        fail(f"{kind} IPA plist does not match its manifest bundle")
    if f"{app_root}_CodeSignature/CodeResources" not in names:
        fail(f"{kind} IPA does not contain a code-signature resource")
    if f"{app_root}embedded.mobileprovision" not in names:
        fail(f"{kind} IPA does not contain an embedded provisioning profile")
    verify_ipa_signature(artifact_path, kind, manifest, plist, app_root, rcodesign)

    if kind == "overte-app":
        if manifest.get("testBuildContractVersion") != 1:
            fail("Overte IPA does not declare E2E contract version 1")
        if (plist.get("OverteE2ETestBuildContractVersion") != 1
                or plist.get("UIFileSharingEnabled") is not True):
            fail("Overte IPA plist does not attest the E2E test-build contract")
    else:
        toolchain = manifest.get("toolchain")
        expected = {
            "xcuitestDriver": lock["appium"]["drivers"]["xcuitest"]["version"],
            "webdriverAgent": lock["appium"]["iosRuntime"]["webdriverAgent"]["version"],
        }
        if toolchain != expected:
            fail("WDA IPA was not produced by the pinned XCUITest/WDA pair")
        if (
            plist.get("OverteE2EWebDriverAgentVersion")
            != expected["webdriverAgent"]
            or plist.get("OverteE2EXCUITestDriverVersion")
            != expected["xcuitestDriver"]
        ):
            fail("WDA IPA plist lacks the pinned XCUITest/WDA pairing markers")
        if not bundle_id.endswith(".xctrunner"):
            fail("WDA bundle identifier must identify the signed XCTest runner")
        xctest = manifest.get("xctest")
        if not isinstance(xctest, dict) or set(xctest) != {"bundle", "signing"}:
            fail("WDA XCTest manifest metadata is invalid")
        nested_bundle = xctest.get("bundle")
        if not isinstance(nested_bundle, dict) or set(nested_bundle) != {"id"}:
            fail("WDA XCTest bundle metadata is invalid")
        nested_bundle_id = nested_bundle.get("id")
        if (not isinstance(nested_bundle_id, str) or not BUNDLE_RE.fullmatch(nested_bundle_id)
                or bundle_id != nested_bundle_id + ".xctrunner"):
            fail("WDA Runner and XCTest bundle identifiers are not the exact pair")
        nested_signing = validate_signing_metadata(
            xctest.get("signing"), nested_bundle_id, "webdriveragent xctest",
            parse_utc(manifest["notAfter"], "webdriveragent notAfter"),
        )
        if nested_signing["teamIdentifier"] != manifest["signing"]["teamIdentifier"]:
            fail("WDA Runner and XCTest teams differ")
        nested_root = f"{app_root}PlugIns/WebDriverAgentRunner.xctest/"
        nested_plist_name = nested_root + "Info.plist"
        required_nested = {
            nested_plist_name,
            nested_root + "embedded.mobileprovision",
            nested_root + "_CodeSignature/CodeResources",
        }
        if not required_nested.issubset(names):
            fail("WDA IPA lacks the signed nested XCTest contract")
        with zipfile.ZipFile(artifact_path) as archive:
            try:
                nested_plist = plistlib.loads(read_member_limited(
                    archive, archive.getinfo(nested_plist_name), MAX_PLIST_BYTES,
                    "webdriveragent xctest plist",
                ))
            except (KeyError, ValueError, plistlib.InvalidFileException):
                fail("WDA XCTest plist is invalid")
        if (not isinstance(nested_plist, dict)
                or nested_plist.get("CFBundleIdentifier") != nested_bundle_id
                or nested_plist.get("CFBundlePackageType") != "BNDL"):
            fail("WDA XCTest plist does not match its manifest bundle")
        verify_ipa_signature(
            artifact_path, "webdriveragent xctest", manifest, nested_plist,
            nested_root, rcodesign, signing=nested_signing, bundle_id=nested_bundle_id,
        )
    return {
        "path": str(artifact_path.resolve()),
        "sha256": digest,
        "bundleId": bundle_id,
    }


def private_tree_sha256(root: Path) -> str:
    try:
        return canonical_tree_sha256(root)
    except ArtifactTreeError as error:
        fail(str(error))


def extract_prebuilt_wda(ipa: Path, destination: Path) -> tuple[Path, str]:
    if (not destination.is_absolute() or has_symlink_component(destination)
            or destination.exists() or destination.is_symlink()):
        fail("prebuilt WDA destination must be new")
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    destination.parent.chmod(0o700)
    plist, app_root, _names = archive_plist(ipa, "webdriveragent")
    if (plist.get("CFBundleIdentifier") != "org.overte.WebDriverAgentRunner.xctrunner"
            or destination.name != PREBUILT_WDA_NAME):
        fail("prebuilt WDA extraction identity is invalid")
    copied_total = 0
    try:
        destination.mkdir(mode=0o700)
        with zipfile.ZipFile(ipa) as archive:
            for entry in archive.infolist():
                if not entry.filename.startswith(app_root):
                    continue
                relative_text = entry.filename[len(app_root):].rstrip("/")
                if not relative_text:
                    continue
                relative = PurePosixPath(relative_text)
                if (relative.is_absolute() or ".." in relative.parts
                        or "\\" in relative_text):
                    fail("prebuilt WDA contains an unsafe relative path")
                target = destination.joinpath(*relative.parts)
                if entry.is_dir():
                    target.mkdir(parents=True, exist_ok=True, mode=0o700)
                    target.chmod(0o700)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                for parent in (target.parent, *target.parent.parents):
                    if parent == destination.parent:
                        break
                    parent.chmod(0o700)
                remaining = MAX_UNCOMPRESSED_BYTES - copied_total
                if remaining <= 0:
                    fail("prebuilt WDA exceeds its cumulative extraction limit")
                if entry.file_size == 0:
                    with target.open("xb") as output:
                        output.flush()
                        os.fsync(output.fileno())
                else:
                    extract_member(
                        archive, entry, target, min(entry.file_size, remaining),
                        f"prebuilt WDA {relative_text}",
                    )
                copied_total += entry.file_size
                source_mode = (entry.external_attr >> 16) & 0o777
                target.chmod(0o700 if source_mode & 0o111 else 0o600)
        if not (destination / "Info.plist").is_file():
            fail("prebuilt WDA extraction lacks Info.plist")
        destination.chmod(0o700)
        return destination.resolve(), private_tree_sha256(destination)
    except BaseException:
        if destination.exists():
            shutil.rmtree(destination, ignore_errors=True)
        raise


def has_symlink_component(path: Path) -> bool:
    absolute = path.expanduser().absolute()
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        if current.is_symlink():
            return True
        if not current.exists():
            break
    return False


def secure_write(path: Path, value: dict) -> None:
    if not path.is_absolute() or has_symlink_component(path):
        fail("receipt path must be an absolute non-symlinked private path")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(temporary, flags, 0o600)
    try:
        payload = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
        with os.fdopen(descriptor, "wb", closefd=False) as output:
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
        os.close(descriptor)
        descriptor = -1
        temporary.replace(path)
        directory = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)


def expected_provenance(arguments: argparse.Namespace) -> dict:
    return {
        "repository": arguments.expected_repository,
        "repositoryId": arguments.expected_repository_id,
        "workflow": PRODUCER_WORKFLOW,
        "reusableWorkflow": REUSABLE_PRODUCER_WORKFLOW,
        "ref": PRODUCER_REF,
        "runId": arguments.expected_run_id,
        "runAttempt": arguments.expected_run_attempt,
    }


def run(arguments: argparse.Namespace) -> int:
    try:
        arguments.receipt.resolve().relative_to(REPOSITORY_ROOT)
        inside_repository = True
    except ValueError:
        inside_repository = False
    if inside_repository:
        fail("signed iOS receipt and extracted WDA must remain outside the repository")
    lock = json.loads(LOCK_FILE.read_text(encoding="utf-8"))
    rcodesign = validate_rcodesign(arguments.rcodesign, lock)
    overte_manifest = load_manifest(arguments.overte_manifest, "overte-app")
    wda_manifest = load_manifest(arguments.wda_manifest, "webdriveragent")
    provenance = expected_provenance(arguments)
    if (overte_manifest["sourceRevision"] != wda_manifest["sourceRevision"]
            or overte_manifest["createdAt"] != wda_manifest["createdAt"]
            or overte_manifest["notAfter"] != wda_manifest["notAfter"]
            or overte_manifest["provenance"] != provenance
            or wda_manifest["provenance"] != provenance):
        fail("Overte and WDA manifests do not match the selected producer attempt")
    overte = verify_one(
        arguments.overte_manifest, arguments.overte_ipa, "overte-app", lock, rcodesign
    )
    wda = verify_one(
        arguments.wda_manifest, arguments.wda_ipa, "webdriveragent", lock, rcodesign
    )
    prebuilt_path, prebuilt_digest = extract_prebuilt_wda(
        arguments.wda_ipa, arguments.receipt.parent / PREBUILT_WDA_NAME
    )
    wda = {
        "ipaPath": wda["path"], "ipaSha256": wda["sha256"],
        "prebuiltPath": str(prebuilt_path), "prebuiltTreeSha256": prebuilt_digest,
        "bundleId": wda["bundleId"],
    }
    receipt = {
        "schemaVersion": 1,
        "contract": RECEIPT_CONTRACT,
        "sourceRevision": overte_manifest["sourceRevision"],
        "createdAt": overte_manifest["createdAt"],
        "notAfter": overte_manifest["notAfter"],
        "provenance": provenance,
        "overte": overte,
        "wda": wda,
        "toolchain": {
            "xcuitestDriver": lock["appium"]["drivers"]["xcuitest"]["version"],
            "remoteXpc": lock["appium"]["iosRuntime"]["remoteXpc"]["version"],
            "webdriverAgent": lock["appium"]["iosRuntime"]["webdriverAgent"]["version"],
        },
    }
    try:
        secure_write(arguments.receipt, receipt)
    except BaseException:
        shutil.rmtree(prebuilt_path, ignore_errors=True)
        raise
    print(f"PASS: verified signed Fedora iOS handoff for {receipt['sourceRevision']}")
    return 0


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--overte-manifest", type=Path, required=True)
    value.add_argument("--overte-ipa", type=Path, required=True)
    value.add_argument("--wda-manifest", type=Path, required=True)
    value.add_argument("--wda-ipa", type=Path, required=True)
    value.add_argument("--receipt", type=Path, required=True)
    value.add_argument("--rcodesign", type=Path, required=True)
    value.add_argument("--expected-repository", required=True)
    value.add_argument("--expected-repository-id", type=int, required=True)
    value.add_argument("--expected-run-id", type=int, required=True)
    value.add_argument("--expected-run-attempt", type=int, required=True)
    return value


def main() -> int:
    try:
        return run(parser().parse_args())
    except (VerificationError, OSError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
