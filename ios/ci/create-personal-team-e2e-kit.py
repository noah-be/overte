#!/usr/bin/env python3
"""Create the credential-free iOS E2E kit for manual Personal Team signing."""

# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import json
import os
import plistlib
import re
import shutil
import stat
import sys
import zipfile
from pathlib import Path, PurePosixPath


CONTRACT = "overte-ios-personal-team-e2e-kit-v1"
OVERTE_BUNDLE_ID = "org.overte.interface.e2e"
WDA_RUNNER_BUNDLE_ID = "org.overte.WebDriverAgentRunner.xctrunner"
WDA_XCTEST_BUNDLE_ID = "org.overte.WebDriverAgentRunner"
WDA_VERSION_KEY = "OverteE2EWebDriverAgentVersion"
XCUITEST_VERSION_KEY = "OverteE2EXCUITestDriverVersion"
XCUITEST_DRIVER_VERSION = "12.8.0"
WDA_VERSION = "16.8.0"
WDA_UPSTREAM_SHA256 = "38ec705d6fa2c7825513adbc9406d4fda5d6a084a8d3980ceff9a265e62f9623"
WDA_UPSTREAM_URL = (
    "https://github.com/appium/WebDriverAgent/releases/download/v16.8.0/"
    "WebDriverAgentRunner-Runner.zip"
)
OVERTE_OUTPUT = "Overte-PersonalTeam-E2E-unsigned.ipa"
WDA_OUTPUT = "WebDriverAgentRunner-16.8.0-PersonalTeam-unsigned.ipa"
MANIFEST_OUTPUT = "personal-team-e2e-kit.json"
MAX_ENTRIES = 65_536
MAX_MEMBER_BYTES = 6 * 1024 * 1024 * 1024
MAX_TOTAL_BYTES = 8 * 1024 * 1024 * 1024
MAX_COMPRESSION_RATIO = 250
MAX_PLIST_BYTES = 4 * 1024 * 1024
MAX_WDA_MEMBER_BYTES = 512 * 1024 * 1024
MAX_WDA_TOTAL_BYTES = 1024 * 1024 * 1024
E2E_BINARY_MARKER = b"Rejected iOS E2E results path outside Documents"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def require_regular_file(path: Path, label: str) -> None:
    try:
        mode = path.lstat().st_mode
    except OSError as error:
        raise ValueError(f"{label} is unavailable") from error
    if not stat.S_ISREG(mode) or path.is_symlink() or path.stat().st_size <= 0:
        raise ValueError(f"{label} must be a non-empty regular file")


def parse_created_at(value: str) -> str:
    if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z", value) is None:
        raise ValueError("createdAt must be a second-precision UTC timestamp")
    try:
        parsed = dt.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=dt.timezone.utc
        )
    except ValueError as error:
        raise ValueError("createdAt is invalid") from error
    if parsed.year < 2026:
        raise ValueError("createdAt is outside the supported time range")
    return value


def safe_member_name(name: str) -> PurePosixPath:
    if not name or "\\" in name or "\x00" in name or name.startswith("/"):
        raise ValueError("archive contains an unsafe member name")
    path = PurePosixPath(name.rstrip("/"))
    if not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("archive contains an unsafe member path")
    return path


def inspect_archive(archive: zipfile.ZipFile, label: str) -> list[zipfile.ZipInfo]:
    entries = archive.infolist()
    if not entries or len(entries) > MAX_ENTRIES:
        raise ValueError(f"{label} archive entry count is invalid")
    names: set[str] = set()
    total = 0
    for entry in entries:
        normalized = str(safe_member_name(entry.filename))
        if normalized in names:
            raise ValueError(f"{label} archive contains duplicate members")
        names.add(normalized)
        mode = entry.external_attr >> 16
        file_type = stat.S_IFMT(mode)
        if file_type == stat.S_IFLNK:
            raise ValueError(f"{label} archive contains a symbolic link")
        if entry.flag_bits & 0x1:
            raise ValueError(f"{label} archive contains an encrypted member")
        if entry.file_size < 0 or entry.file_size > MAX_MEMBER_BYTES:
            raise ValueError(f"{label} archive member is too large")
        if not entry.is_dir():
            if file_type not in {0, stat.S_IFREG}:
                raise ValueError(f"{label} archive contains a non-regular member")
            if entry.file_size and entry.compress_size == 0:
                raise ValueError(f"{label} archive member has an invalid compressed size")
            if (
                entry.file_size > 1024 * 1024
                and entry.file_size > entry.compress_size * MAX_COMPRESSION_RATIO
            ):
                raise ValueError(f"{label} archive exceeds the compression-ratio limit")
        total += entry.file_size
        if total > MAX_TOTAL_BYTES:
            raise ValueError(f"{label} archive expands beyond the size limit")
    return entries


def read_plist_member(
    archive: zipfile.ZipFile, entries: list[zipfile.ZipInfo], name: str
) -> dict:
    matches = [entry for entry in entries if entry.filename.rstrip("/") == name]
    if len(matches) != 1 or matches[0].is_dir() or matches[0].file_size > MAX_PLIST_BYTES:
        raise ValueError(f"archive must contain exactly one bounded {name}")
    try:
        payload = plistlib.loads(archive.read(matches[0]))
    except plistlib.InvalidFileException as error:
        raise ValueError(f"{name} is not a valid plist") from error
    if not isinstance(payload, dict):
        raise ValueError(f"{name} plist root is not a dictionary")
    return payload


def archive_member(entries: list[zipfile.ZipInfo], name: str) -> zipfile.ZipInfo:
    matches = [entry for entry in entries if entry.filename.rstrip("/") == name]
    if len(matches) != 1 or matches[0].is_dir():
        raise ValueError(f"archive must contain exactly one regular {name}")
    return matches[0]


def stream_contains(archive: zipfile.ZipFile, entry: zipfile.ZipInfo, marker: bytes) -> bool:
    overlap = b""
    remaining = entry.file_size
    with archive.open(entry) as stream:
        while remaining:
            chunk = stream.read(min(1024 * 1024, remaining))
            if not chunk:
                raise ValueError("archive executable is truncated")
            remaining -= len(chunk)
            candidate = overlap + chunk
            if marker in candidate:
                return True
            overlap = candidate[-(len(marker) - 1) :]
    return False


def validate_overte(
    ipa: Path, integrated_manifest: Path, source_revision: str
) -> None:
    require_regular_file(ipa, "unsigned Overte IPA")
    require_regular_file(integrated_manifest, "unsigned Overte manifest")
    if ipa.stat().st_size > MAX_MEMBER_BYTES:
        raise ValueError("unsigned Overte IPA is too large")
    try:
        manifest = json.loads(integrated_manifest.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("unsigned Overte manifest is invalid") from error
    expected = {
        "schemaVersion": 1,
        "product": "overte-ios-integrated-client",
        "artifact": ipa.name,
        "sourceRevision": source_revision,
        "platform": "iphoneos",
        "architecture": "arm64",
        "configuration": "Release",
        "signed": False,
        "requiresSigning": True,
        "testBuildContractVersion": 1,
    }
    if not isinstance(manifest, dict) or any(
        manifest.get(key) != value for key, value in expected.items()
    ):
        raise ValueError("unsigned Overte manifest contract mismatch")
    if manifest.get("sha256") != sha256_file(ipa):
        raise ValueError("unsigned Overte IPA does not match its manifest SHA-256")
    signing = manifest.get("signing")
    if not isinstance(signing, dict) or signing != {
        "embeddedProvisioningProfile": False,
        "applicationIdentifier": None,
        "getTaskAllow": None,
    }:
        raise ValueError("unsigned Overte manifest unexpectedly contains signing metadata")
    with zipfile.ZipFile(ipa) as archive:
        entries = inspect_archive(archive, "Overte")
        names = {entry.filename.rstrip("/") for entry in entries}
        if any(
            name not in {"Payload", "Payload/Overte.app"}
            and not name.startswith("Payload/Overte.app/")
            for name in names
        ):
            raise ValueError("unsigned Overte IPA contains content outside its application")
        info = read_plist_member(archive, entries, "Payload/Overte.app/Info.plist")
        executable = archive_member(entries, "Payload/Overte.app/Overte")
        if info.get("CFBundleIdentifier") != OVERTE_BUNDLE_ID:
            raise ValueError("unsigned Overte IPA does not use the fixed E2E bundle identifier")
        if info.get("OverteE2ETestBuildContractVersion") != 1:
            raise ValueError("unsigned Overte IPA lacks E2E test-build contract version 1")
        if info.get("UIFileSharingEnabled") is not True:
            raise ValueError("unsigned Overte IPA does not enable controlled Documents access")
        if not stream_contains(archive, executable, E2E_BINARY_MARKER):
            raise ValueError("unsigned Overte IPA lacks its opt-in E2E runtime boundary")
        forbidden = (
            "Payload/Overte.app/embedded.mobileprovision",
            "Payload/Overte.app/_CodeSignature",
        )
        if any(name == forbidden[0] or name.startswith(forbidden[1] + "/") for name in names):
            raise ValueError("unsigned Overte IPA contains private signing material")


def is_signing_member(relative: PurePosixPath) -> bool:
    return any(part == "_CodeSignature" for part in relative.parts) or relative.name in {
        "embedded.mobileprovision",
        "embedded.provisionprofile",
    }


def create_unsigned_wda(upstream: Path, output: Path) -> None:
    require_regular_file(upstream, "WebDriverAgent upstream archive")
    if sha256_file(upstream) != WDA_UPSTREAM_SHA256:
        raise ValueError("WebDriverAgent upstream archive SHA-256 mismatch")
    app_root = PurePosixPath("WebDriverAgentRunner-Runner.app")
    runner_info = app_root / "Info.plist"
    xctest_info = app_root / "PlugIns/WebDriverAgentRunner.xctest/Info.plist"
    rewritten: set[PurePosixPath] = set()
    with zipfile.ZipFile(upstream) as source:
        entries = inspect_archive(source, "WebDriverAgent")
        if (
            any(entry.file_size > MAX_WDA_MEMBER_BYTES for entry in entries)
            or sum(entry.file_size for entry in entries) > MAX_WDA_TOTAL_BYTES
        ):
            raise ValueError("WebDriverAgent archive expands beyond its role-specific limit")
        for entry in entries:
            member = safe_member_name(entry.filename)
            if member.parts[: len(app_root.parts)] != app_root.parts:
                raise ValueError("WebDriverAgent archive contains content outside its application")
        with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED) as target:
            for entry in entries:
                member = safe_member_name(entry.filename)
                relative = PurePosixPath(*member.parts[len(app_root.parts) :])
                if not relative.parts or is_signing_member(relative):
                    continue
                target_entry = copy.copy(entry)
                target_name = str(PurePosixPath("Payload") / app_root / relative)
                if entry.is_dir():
                    target_entry.filename = target_name + "/"
                    target.writestr(target_entry, b"")
                    continue
                target_entry.filename = target_name
                if member in {runner_info, xctest_info}:
                    data = source.read(entry)
                    try:
                        info = plistlib.loads(data)
                    except plistlib.InvalidFileException as error:
                        raise ValueError("WebDriverAgent contains an invalid Info.plist") from error
                    if not isinstance(info, dict):
                        raise ValueError("WebDriverAgent Info.plist root is not a dictionary")
                    info["CFBundleIdentifier"] = (
                        WDA_RUNNER_BUNDLE_ID if member == runner_info else WDA_XCTEST_BUNDLE_ID
                    )
                    if member == runner_info:
                        info[WDA_VERSION_KEY] = WDA_VERSION
                        info[XCUITEST_VERSION_KEY] = XCUITEST_DRIVER_VERSION
                    data = plistlib.dumps(info, fmt=plistlib.FMT_BINARY, sort_keys=True)
                    target_entry.file_size = len(data)
                    target_entry.CRC = 0
                    target_entry.compress_size = 0
                    rewritten.add(member)
                    target.writestr(target_entry, data)
                else:
                    with source.open(entry) as input_stream, target.open(
                        target_entry, "w"
                    ) as output_stream:
                        shutil.copyfileobj(input_stream, output_stream, 1024 * 1024)
    if rewritten != {runner_info, xctest_info}:
        output.unlink(missing_ok=True)
        raise ValueError("WebDriverAgent archive lacks the runner or nested XCTest Info.plist")
    output.chmod(0o644)


def validate_unsigned_wda(path: Path) -> None:
    with zipfile.ZipFile(path) as archive:
        entries = inspect_archive(archive, "normalized WebDriverAgent")
        root = "Payload/WebDriverAgentRunner-Runner.app"
        runner = read_plist_member(archive, entries, f"{root}/Info.plist")
        xctest = read_plist_member(
            archive, entries, f"{root}/PlugIns/WebDriverAgentRunner.xctest/Info.plist"
        )
        if runner.get("CFBundleIdentifier") != WDA_RUNNER_BUNDLE_ID:
            raise ValueError("WebDriverAgent runner bundle identifier normalization failed")
        if (runner.get(WDA_VERSION_KEY) != WDA_VERSION
                or runner.get(XCUITEST_VERSION_KEY) != XCUITEST_DRIVER_VERSION):
            raise ValueError("WebDriverAgent runner lacks the pinned E2E toolchain markers")
        if xctest.get("CFBundleIdentifier") != WDA_XCTEST_BUNDLE_ID:
            raise ValueError("WebDriverAgent XCTest bundle identifier normalization failed")
        names = {entry.filename.rstrip("/") for entry in entries}
        if any(
            "/_CodeSignature/" in f"/{name}/"
            or name.endswith("/embedded.mobileprovision")
            or name.endswith("/embedded.provisionprofile")
            for name in names
        ):
            raise ValueError("normalized WebDriverAgent contains private signing material")


def create_kit(
    overte_ipa: Path,
    overte_manifest: Path,
    wda_upstream: Path,
    output_dir: Path,
    source_revision: str,
    created_at: str,
    source_repository: str,
    source_repository_id: int,
    source_ref: str,
    workflow: str,
    reusable_workflow: str,
    run_id: int,
    run_attempt: int,
) -> dict:
    if re.fullmatch(r"[0-9a-f]{40}", source_revision) is None:
        raise ValueError("source revision must be a lowercase 40-character Git SHA")
    created_at = parse_created_at(created_at)
    if re.fullmatch(r"[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}", source_repository) is None:
        raise ValueError("source repository is invalid")
    if not isinstance(source_repository_id, int) or source_repository_id <= 0:
        raise ValueError("source repository ID must be positive")
    if source_ref != "refs/heads/apple-ios":
        raise ValueError("source ref must be the protected apple-ios branch")
    if workflow != ".github/workflows/ios-bootstrap.yml":
        raise ValueError("workflow provenance must name the registered bootstrap")
    if reusable_workflow != ".github/workflows/ios-personal-team-e2e-kit.yml":
        raise ValueError("reusable workflow provenance is invalid")
    if not isinstance(run_id, int) or run_id <= 0:
        raise ValueError("run ID must be positive")
    if not isinstance(run_attempt, int) or run_attempt <= 0:
        raise ValueError("run attempt must be positive")
    if output_dir.exists():
        raise ValueError("output directory must not already exist")
    validate_overte(overte_ipa, overte_manifest, source_revision)
    output_dir.mkdir(mode=0o755, parents=False)
    overte_output = output_dir / OVERTE_OUTPUT
    wda_output = output_dir / WDA_OUTPUT
    try:
        shutil.copyfile(overte_ipa, overte_output)
        overte_output.chmod(0o644)
        create_unsigned_wda(wda_upstream, wda_output)
        validate_unsigned_wda(wda_output)
        payload = {
            "schemaVersion": 1,
            "contract": CONTRACT,
            "sourceRevision": source_revision,
            "createdAt": created_at,
            "provenance": {
                "repository": source_repository,
                "repositoryId": source_repository_id,
                "workflow": workflow,
                "reusableWorkflow": reusable_workflow,
                "ref": source_ref,
                "runId": run_id,
                "runAttempt": run_attempt,
            },
            "xcuitestDriverVersion": XCUITEST_DRIVER_VERSION,
            "webDriverAgentVersion": WDA_VERSION,
            "desiredBundleIdentifiers": {
                "overte": OVERTE_BUNDLE_ID,
                "wdaRunner": WDA_RUNNER_BUNDLE_ID,
                "wdaXCTest": WDA_XCTEST_BUNDLE_ID,
            },
            "humanSigningBoundary": {
                "method": "manual-sideloadly-personal-team",
                "derivationBinding": "human-verified",
                "signedBytesDerivableFromUnsignedKit": False,
                "maximumProfileLifetimeDays": 7,
            },
            "upstream": {
                "webDriverAgentUrl": WDA_UPSTREAM_URL,
                "webDriverAgentSha256": WDA_UPSTREAM_SHA256,
            },
            "artifacts": {
                "overte": {
                    "name": overte_output.name,
                    "sha256": sha256_file(overte_output),
                    "size": overte_output.stat().st_size,
                },
                "webDriverAgent": {
                    "name": wda_output.name,
                    "sha256": sha256_file(wda_output),
                    "size": wda_output.stat().st_size,
                },
            },
        }
        manifest = output_dir / MANIFEST_OUTPUT
        with manifest.open("x", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2, sort_keys=True)
            stream.write("\n")
        manifest.chmod(0o644)
        return payload
    except Exception:
        shutil.rmtree(output_dir, ignore_errors=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--overte-ipa", type=Path, required=True)
    parser.add_argument("--overte-manifest", type=Path, required=True)
    parser.add_argument("--wda-upstream", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--created-at", required=True)
    parser.add_argument("--source-repository", required=True)
    parser.add_argument("--source-repository-id", type=int, required=True)
    parser.add_argument("--source-ref", required=True)
    parser.add_argument("--workflow", required=True)
    parser.add_argument("--reusable-workflow", required=True)
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument("--run-attempt", type=int, required=True)
    args = parser.parse_args()
    try:
        create_kit(
            args.overte_ipa,
            args.overte_manifest,
            args.wda_upstream,
            args.output_dir,
            args.source_revision,
            args.created_at,
            args.source_repository,
            args.source_repository_id,
            args.source_ref,
            args.workflow,
            args.reusable_workflow,
            args.run_id,
            args.run_attempt,
        )
    except (OSError, ValueError, zipfile.BadZipFile) as error:
        print(f"error: Personal Team E2E kit rejected: {error}", file=sys.stderr)
        return 1
    print("PASS credential-free Personal Team E2E kit")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
