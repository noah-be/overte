#!/usr/bin/env python3
"""Verify signed iOS E2E/WDA handoff artifacts and write a private Fedora receipt."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
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
import zipfile


DEVICE_ROOT = Path(__file__).resolve().parents[1]
LOCK_FILE = DEVICE_ROOT / "toolchain.lock.json"
ARTIFACT_CONTRACT = "overte-ios-fedora-e2e-artifact-v1"
RECEIPT_CONTRACT = "overte-ios-fedora-e2e-receipt-v1"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
REVISION_RE = re.compile(r"^[0-9a-f]{40}$")
BUNDLE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]*(?:\.[A-Za-z0-9][A-Za-z0-9-]*)+$")
MAX_ARCHIVE_ENTRIES = 200_000
MAX_UNCOMPRESSED_BYTES = 12 * 1024 * 1024 * 1024
MAX_PLIST_BYTES = 4 * 1024 * 1024
MAX_EXECUTABLE_BYTES = 2 * 1024 * 1024 * 1024
MAX_PROFILE_BYTES = 32 * 1024 * 1024


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


def load_manifest(path: Path, kind: str) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        fail(f"{kind} manifest is unreadable: {type(error).__name__}")
    if not isinstance(value, dict):
        fail(f"{kind} manifest must be an object")
    common = {
        "schemaVersion", "contract", "kind", "sourceRevision", "artifact",
        "bundle", "signing",
    }
    expected = common | ({"testBuildContractVersion"} if kind == "overte-app" else {"toolchain"})
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
    if not artifact_path.is_file() or artifact_path.stat().st_size != artifact["size"]:
        fail(f"{kind} artifact bytes do not match the manifest size")
    actual_sha = sha256_file(artifact_path)
    if actual_sha != artifact["sha256"]:
        fail(f"{kind} artifact failed its SHA-256")

    bundle = manifest.get("bundle")
    if not isinstance(bundle, dict) or set(bundle) != {"id"}:
        fail(f"{kind} bundle metadata is invalid")
    bundle_id = bundle.get("id")
    if not isinstance(bundle_id, str) or not BUNDLE_RE.fullmatch(bundle_id):
        fail(f"{kind} bundle identifier is invalid")

    signing = manifest.get("signing")
    if not isinstance(signing, dict) or set(signing) != {
        "signed", "teamIdentifier", "applicationIdentifier", "profileExpiration"
    }:
        fail(f"{kind} signing metadata is invalid")
    team = signing.get("teamIdentifier")
    if signing.get("signed") is not True or not isinstance(team, str) or not team:
        fail(f"{kind} must be signed by an identified development team")
    if signing.get("applicationIdentifier") != f"{team}.{bundle_id}":
        fail(f"{kind} application identifier does not match team and bundle")
    expiration = signing.get("profileExpiration")
    if not isinstance(expiration, str):
        fail(f"{kind} profile expiration is missing")
    try:
        expiry = datetime.fromisoformat(expiration.replace("Z", "+00:00"))
    except ValueError:
        fail(f"{kind} profile expiration is not ISO-8601")
    if expiry.tzinfo is None or expiry <= datetime.now(timezone.utc):
        fail(f"{kind} provisioning profile is expired")
    return bundle_id, actual_sha


def archive_plist(artifact_path: Path, kind: str) -> tuple[dict, str, set[str]]:
    try:
        archive = zipfile.ZipFile(artifact_path)
    except (OSError, zipfile.BadZipFile):
        fail(f"{kind} artifact is not a valid IPA ZIP archive")
    with archive:
        entries = archive.infolist()
        if not entries or len(entries) > MAX_ARCHIVE_ENTRIES:
            fail(f"{kind} IPA entry count is invalid")
        if sum(entry.file_size for entry in entries) > MAX_UNCOMPRESSED_BYTES:
            fail(f"{kind} IPA expands beyond the safety limit")
        names: set[str] = set()
        for entry in entries:
            name = entry.filename
            path = PurePosixPath(name)
            if (not name or path.is_absolute() or "\\" in name
                    or any(part in {"", ".", ".."} for part in path.parts)
                    or entry.flag_bits & 0x1):
                fail(f"{kind} IPA contains an unsafe entry")
            mode = (entry.external_attr >> 16) & 0o170000
            if mode == stat.S_IFLNK:
                fail(f"{kind} IPA contains a symbolic link")
            if name in names:
                fail(f"{kind} IPA contains duplicate entries")
            names.add(name)
        plist_names = [
            name for name in names
            if re.fullmatch(r"Payload/[^/]+[.]app/Info[.]plist", name)
        ]
        if len(plist_names) != 1:
            fail(f"{kind} IPA must contain exactly one top-level application plist")
        plist_name = plist_names[0]
        info = archive.getinfo(plist_name)
        if info.file_size > MAX_PLIST_BYTES:
            fail(f"{kind} application plist exceeds the safety limit")
        try:
            plist = plistlib.loads(archive.read(plist_name))
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


def verify_ipa_signature(artifact_path: Path, kind: str, manifest: dict, plist: dict,
                         app_root: str, rcodesign: Path) -> None:
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
            executable.write_bytes(archive.read(executable_info))
            profile.write_bytes(archive.read(profile_info))
            executable.chmod(0o700)
            signature = subprocess.run(
                [str(rcodesign), "verify", "--config-file", "/dev/null", str(executable)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=120, check=False,
            )
            if signature.returncode:
                fail(f"{kind} Mach-O code signature failed cryptographic verification")
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

    signing = manifest["signing"]
    team = signing["teamIdentifier"]
    teams = profile_plist.get("TeamIdentifier")
    entitlements = profile_plist.get("Entitlements")
    expiration = profile_plist.get("ExpirationDate")
    if not isinstance(teams, list) or team not in teams or not isinstance(entitlements, dict):
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
    manifest_expiry = datetime.fromisoformat(
        signing["profileExpiration"].replace("Z", "+00:00")
    )
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
        if not bundle_id.endswith(".xctrunner"):
            fail("WDA bundle identifier must identify the signed XCTest runner")
    return {
        "path": str(artifact_path.resolve()),
        "sha256": digest,
        "bundleId": bundle_id,
    }


def secure_write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if os.name != "nt":
        temporary.chmod(stat.S_IRUSR | stat.S_IWUSR)
    temporary.replace(path)


def run(arguments: argparse.Namespace) -> int:
    lock = json.loads(LOCK_FILE.read_text(encoding="utf-8"))
    rcodesign = validate_rcodesign(arguments.rcodesign, lock)
    overte_manifest = load_manifest(arguments.overte_manifest, "overte-app")
    wda_manifest = load_manifest(arguments.wda_manifest, "webdriveragent")
    if overte_manifest["sourceRevision"] != wda_manifest["sourceRevision"]:
        fail("Overte and WDA artifacts must be bound to the same source revision")
    overte = verify_one(
        arguments.overte_manifest, arguments.overte_ipa, "overte-app", lock, rcodesign
    )
    wda = verify_one(
        arguments.wda_manifest, arguments.wda_ipa, "webdriveragent", lock, rcodesign
    )
    receipt = {
        "schemaVersion": 1,
        "contract": RECEIPT_CONTRACT,
        "sourceRevision": overte_manifest["sourceRevision"],
        "overte": overte,
        "wda": wda,
        "toolchain": {
            "xcuitestDriver": lock["appium"]["drivers"]["xcuitest"]["version"],
            "remoteXpc": lock["appium"]["iosRuntime"]["remoteXpc"]["version"],
            "webdriverAgent": lock["appium"]["iosRuntime"]["webdriverAgent"]["version"],
        },
    }
    secure_write(arguments.receipt, receipt)
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
    return value


def main() -> int:
    try:
        return run(parser().parse_args())
    except (VerificationError, OSError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
