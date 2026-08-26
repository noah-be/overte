#!/usr/bin/env python3
"""Verify an exact integrated-client artifact before simulator or iPad use."""

# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import plistlib
import re
import stat
import struct
import sys
import zipfile
from pathlib import Path, PurePosixPath


REVISION = re.compile(r"[0-9a-f]{40}")
DIGEST = re.compile(r"[0-9a-f]{64}")
SAFE_ARTIFACT = re.compile(
    r"[0-9]{4,}-OverteIOSClient-[A-Za-z0-9][A-Za-z0-9._]*-"
    r"(?:simulator[.]zip|device-signed[.]ipa)"
)
FEDORA_CONTRACT = "overte-ios-fedora-e2e-artifact-v1"
BUNDLE_ID = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9-]*(?:[.][A-Za-z0-9][A-Za-z0-9-]*)+"
)
APPLE_VERSION = re.compile(r"[0-9]+(?:[.][0-9]+){0,2}")
MAX_ARCHIVE_BYTES = 1024 * 1024 * 1024
MAX_EXPANDED_BYTES = 2 * 1024 * 1024 * 1024
MAX_MEMBERS = 20_000
MAX_PLIST_BYTES = 1024 * 1024
MAX_MACHO_COMMAND_BYTES = 4 * 1024 * 1024
MACHO_64_MAGIC = 0xFEEDFACF
CPU_TYPE_ARM64 = 0x0100000C
LC_BUILD_VERSION = 0x32
PLATFORM_IOS = 2
PLATFORM_IOS_SIMULATOR = 7


def load_handoff_verifier():
    path = Path(__file__).with_name("verify-windows-handoff.py")
    specification = importlib.util.spec_from_file_location("runtime_candidate_handoff", path)
    if specification is None or specification.loader is None:
        raise RuntimeError("cannot load the integrated-client handoff verifier")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def load_static_runtime_verifier():
    path = Path(__file__).with_name("verify-ios-static-runtime.py")
    specification = importlib.util.spec_from_file_location("runtime_candidate_static", path)
    if specification is None or specification.loader is None:
        raise RuntimeError("cannot load the static iOS runtime verifier")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def normalized_member_name(raw_name: str) -> str:
    if not raw_name or "\0" in raw_name or "\\" in raw_name:
        raise ValueError("artifact contains an unsafe ZIP entry")
    if raw_name.startswith("/") or re.match(r"^[A-Za-z]:", raw_name):
        raise ValueError("artifact contains an unsafe ZIP entry")
    name = raw_name[:-1] if raw_name.endswith("/") else raw_name
    if not name:
        raise ValueError("artifact contains an unsafe ZIP entry")
    parts = name.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError("artifact contains an unsafe ZIP entry")
    return "/".join(parts)


def is_metadata(name: str) -> bool:
    return name == "__MACOSX" or name.startswith("__MACOSX/")


def app_roots(names: set[str]) -> set[str]:
    roots: set[str] = set()
    for name in names:
        if is_metadata(name):
            continue
        parts = name.split("/")
        for index, part in enumerate(parts):
            if part.endswith(".app"):
                roots.add("/".join(parts[: index + 1]))
    return roots


def resolve_link_target(link_name: str, raw_target: str) -> str:
    if not raw_target or "\0" in raw_target or "\\" in raw_target:
        raise ValueError("artifact contains an unsafe symlink target")
    if raw_target.startswith("/") or re.match(r"^[A-Za-z]:", raw_target):
        raise ValueError("artifact contains an unsafe symlink target")
    target_parts = raw_target.split("/")
    if any(part == "" for part in target_parts):
        raise ValueError("artifact contains an unsafe symlink target")
    resolved = list(PurePosixPath(link_name).parent.parts)
    for part in target_parts:
        if part == ".":
            continue
        if part == "..":
            if not resolved:
                raise ValueError("artifact symlink escapes the application bundle")
            resolved.pop()
        else:
            resolved.append(part)
    if not resolved:
        raise ValueError("artifact symlink escapes the application bundle")
    return "/".join(resolved)


def is_within(path: str, root: str) -> bool:
    return path == root or path.startswith(root + "/")


def require_regular_file(
    members: dict[str, zipfile.ZipInfo], name: str, description: str
) -> zipfile.ZipInfo:
    info = members.get(name)
    if info is None or info.is_dir() or stat.S_ISLNK(info.external_attr >> 16):
        raise ValueError(f"artifact is missing {description}")
    if info.file_size <= 0:
        raise ValueError(f"artifact has an empty {description}")
    return info


def require_arm64_macho(
    archive: zipfile.ZipFile, entry: zipfile.ZipInfo, mode: str
) -> None:
    static_runtime_verifier = load_static_runtime_verifier()
    with archive.open(entry) as stream:
        header = stream.read(32)
        if len(header) != 32:
            raise ValueError("Overte executable has no complete Mach-O header")
        magic, cpu_type, _subtype, _filetype, command_count, command_size, _flags, _reserved = (
            struct.unpack("<IiiIIIII", header)
        )
        if magic != MACHO_64_MAGIC or cpu_type != CPU_TYPE_ARM64:
            raise ValueError("Overte executable is not a thin arm64 Mach-O")
        if command_count > 4096 or command_size > MAX_MACHO_COMMAND_BYTES:
            raise ValueError("Overte executable has unreasonable Mach-O commands")
        commands = stream.read(command_size)
        static_runtime_verifier.audit_ios_ui_markers(stream)
    if len(commands) != command_size:
        raise ValueError("Overte executable has truncated Mach-O commands")

    platforms: list[int] = []
    offset = 0
    for _ in range(command_count):
        if offset + 8 > len(commands):
            raise ValueError("Overte executable has malformed Mach-O commands")
        command, size = struct.unpack_from("<II", commands, offset)
        if size < 8 or offset + size > len(commands):
            raise ValueError("Overte executable has malformed Mach-O commands")
        if command == LC_BUILD_VERSION:
            if size < 24:
                raise ValueError("Overte executable has a malformed build-version command")
            platforms.append(struct.unpack_from("<I", commands, offset + 8)[0])
        offset += size
    if offset != len(commands):
        raise ValueError("Overte executable Mach-O command size mismatch")
    static_runtime_verifier.audit_macho_parts(header, commands)
    expected = PLATFORM_IOS_SIMULATOR if mode == "simulator" else PLATFORM_IOS
    if platforms != [expected]:
        raise ValueError("Overte executable targets the wrong Apple platform")


def inspect_archive(artifact: Path, mode: str) -> tuple[str, str]:
    expected_root = "Overte.app" if mode == "simulator" else "Payload/Overte.app"
    with zipfile.ZipFile(artifact) as archive:
        infos = archive.infolist()
        if not infos:
            raise ValueError("artifact ZIP is empty")
        if len(infos) > MAX_MEMBERS:
            raise ValueError("artifact ZIP contains too many entries")
        if sum(info.file_size for info in infos) > MAX_EXPANDED_BYTES:
            raise ValueError("artifact ZIP expands beyond the runtime limit")
        if archive.testzip() is not None:
            raise ValueError("artifact ZIP has a corrupt entry")

        members: dict[str, zipfile.ZipInfo] = {}
        for info in infos:
            name = normalized_member_name(info.filename)
            if name in members:
                raise ValueError("artifact contains duplicate ZIP entries")
            if info.flag_bits & 0x1:
                raise ValueError("artifact contains an encrypted ZIP entry")
            file_type = stat.S_IFMT(info.external_attr >> 16)
            if file_type not in {0, stat.S_IFREG, stat.S_IFDIR, stat.S_IFLNK}:
                raise ValueError("artifact contains an unsupported special ZIP entry")
            members[name] = info

        roots = app_roots(set(members))
        if roots != {expected_root}:
            raise ValueError(
                f"artifact must contain exactly one application root: {expected_root}"
            )

        for name, info in members.items():
            if is_metadata(name):
                if stat.S_ISLNK(info.external_attr >> 16):
                    raise ValueError("artifact metadata must not contain symlinks")
                continue
            if mode == "simulator":
                if not is_within(name, expected_root):
                    raise ValueError("simulator ZIP contains content outside Overte.app")
            elif name != "Payload" and not is_within(name, expected_root):
                raise ValueError("iPad IPA contains content outside Payload/Overte.app")

            if not stat.S_ISLNK(info.external_attr >> 16):
                continue
            if not is_within(name, expected_root):
                raise ValueError("artifact symlink is outside the application bundle")
            if info.file_size > 4096:
                raise ValueError("artifact symlink target is unreasonably large")
            try:
                target_text = archive.read(info).decode("utf-8")
            except UnicodeDecodeError as error:
                raise ValueError("artifact symlink target is not UTF-8") from error
            target = resolve_link_target(name, target_text)
            if not is_within(target, expected_root):
                raise ValueError("artifact symlink escapes the application bundle")
            if target not in members and not any(
                member.startswith(target + "/") for member in members
            ):
                raise ValueError("artifact symlink target does not exist")

        info_name = f"{expected_root}/Info.plist"
        info_entry = require_regular_file(members, info_name, "Overte.app Info.plist")
        if info_entry.file_size > MAX_PLIST_BYTES:
            raise ValueError("Overte.app Info.plist is unreasonably large")
        executable_entry = require_regular_file(
            members, f"{expected_root}/Overte", "Overte executable"
        )
        require_regular_file(
            members, f"{expected_root}/PrivacyInfo.xcprivacy", "privacy manifest"
        )
        if stat.S_ISLNK(executable_entry.external_attr >> 16):
            raise ValueError("Overte executable must not be a symlink")
        executable_mode = executable_entry.external_attr >> 16
        if executable_mode and executable_mode & 0o111 == 0:
            raise ValueError("Overte executable is not marked executable")
        require_arm64_macho(archive, executable_entry, mode)
        try:
            bundle_info = plistlib.loads(archive.read(info_entry))
        except plistlib.InvalidFileException as error:
            raise ValueError("Overte.app Info.plist is invalid") from error
        if not isinstance(bundle_info, dict):
            raise ValueError("Overte.app Info.plist root is not a dictionary")
        if bundle_info.get("CFBundleExecutable") != "Overte":
            raise ValueError("Info.plist does not select the Overte executable")
        if APPLE_VERSION.fullmatch(str(bundle_info.get("CFBundleShortVersionString", ""))) is None:
            raise ValueError("Info.plist has no valid marketing version")
        if APPLE_VERSION.fullmatch(str(bundle_info.get("CFBundleVersion", ""))) is None:
            raise ValueError("Info.plist has no valid build version")
        expected_platform = "iPhoneSimulator" if mode == "simulator" else "iPhoneOS"
        if bundle_info.get("CFBundleSupportedPlatforms") != [expected_platform]:
            raise ValueError("Info.plist targets the wrong Apple platform")
        if set(bundle_info.get("UIDeviceFamily", [])) != {1, 2}:
            raise ValueError("Info.plist must support iPhone and iPad")
        if bundle_info.get("LSRequiresIPhoneOS") is not True:
            raise ValueError("Info.plist is not an iOS application")
        bundle_id = bundle_info.get("CFBundleIdentifier")
        if (
            not isinstance(bundle_id, str)
            or BUNDLE_ID.fullmatch(bundle_id) is None
            or ".." in bundle_id
        ):
            raise ValueError("Info.plist has an invalid bundle identifier")

        if mode == "ipad":
            require_regular_file(
                members,
                f"{expected_root}/embedded.mobileprovision",
                "embedded provisioning profile",
            )
            require_regular_file(
                members,
                f"{expected_root}/_CodeSignature/CodeResources",
                "code-signature resources",
            )

    return expected_root, bundle_id


def require_e2e_contract(artifact: Path, app_root: str) -> None:
    with zipfile.ZipFile(artifact) as archive:
        try:
            info = plistlib.loads(archive.read(f"{app_root}/Info.plist"))
        except KeyError as error:
            raise ValueError("E2E candidate has no Info.plist") from error
    if not isinstance(info, dict):
        raise ValueError("E2E candidate Info.plist root is invalid")
    if info.get("OverteE2ETestBuildContractVersion") != 1:
        raise ValueError("E2E candidate contract version mismatch")
    if info.get("UIFileSharingEnabled") is not True:
        raise ValueError("E2E candidate does not export test results through Files")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def find_fedora_manifest(directory: Path) -> dict | None:
    matching: list[dict] = []
    for path in directory.glob("*.manifest.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise ValueError("Fedora E2E manifest is invalid JSON") from error
        if isinstance(payload, dict) and payload.get("contract") == FEDORA_CONTRACT:
            matching.append(payload)
    if not matching:
        return None
    if len(matching) != 1:
        raise ValueError("candidate contains multiple Fedora E2E manifests")
    return matching[0]


def verify_fedora_candidate(
    directory: Path, payload: dict, expected_source_revision: str, expected_sha256: str
) -> dict:
    if payload.get("schemaVersion") != 1 or payload.get("kind") != "overte-app":
        raise ValueError("Fedora E2E manifest does not select an Overte app")
    if payload.get("sourceRevision") != expected_source_revision:
        raise ValueError("Fedora E2E source revision mismatch")
    if payload.get("testBuildContractVersion") != 1:
        raise ValueError("Fedora E2E test-build contract version mismatch")
    artifact_info = payload.get("artifact")
    bundle = payload.get("bundle")
    signing = payload.get("signing")
    if not all(isinstance(value, dict) for value in (artifact_info, bundle, signing)):
        raise ValueError("Fedora E2E manifest structure is invalid")
    artifact_name = artifact_info.get("name")
    if not isinstance(artifact_name, str) or SAFE_ARTIFACT.fullmatch(artifact_name) is None:
        raise ValueError("Fedora E2E artifact name is invalid")
    if artifact_info.get("sha256") != expected_sha256:
        raise ValueError("Fedora E2E approved SHA-256 mismatch")
    artifact = directory / artifact_name
    if not artifact.is_file() or artifact.stat().st_size != artifact_info.get("size"):
        raise ValueError("Fedora E2E artifact size mismatch")
    if artifact.stat().st_size > MAX_ARCHIVE_BYTES or sha256_file(artifact) != expected_sha256:
        raise ValueError("Fedora E2E artifact SHA-256 mismatch")
    bundle_id = bundle.get("id")
    if not isinstance(bundle_id, str) or BUNDLE_ID.fullmatch(bundle_id) is None or not bundle_id.endswith(".e2e"):
        raise ValueError("Fedora E2E bundle identifier is invalid")
    application_identifier = signing.get("applicationIdentifier")
    team_identifier = signing.get("teamIdentifier")
    if signing.get("signed") is not True:
        raise ValueError("Fedora E2E artifact is not declared signed")
    if not isinstance(team_identifier, str) or not re.fullmatch(r"[A-Z0-9]{10}", team_identifier):
        raise ValueError("Fedora E2E team identifier is invalid")
    if application_identifier != f"{team_identifier}.{bundle_id}":
        raise ValueError("Fedora E2E application identifier mismatch")
    expiration = signing.get("profileExpiration")
    if not isinstance(expiration, str):
        raise ValueError("Fedora E2E profile expiration is missing")
    try:
        expires = dt.datetime.fromisoformat(expiration.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("Fedora E2E profile expiration is invalid") from error
    if expires.tzinfo is None or expires <= dt.datetime.now(dt.timezone.utc):
        raise ValueError("Fedora E2E provisioning profile is expired")
    app_root, archived_bundle_id = inspect_archive(artifact, "ipad")
    if archived_bundle_id != bundle_id:
        raise ValueError("Fedora E2E archive bundle identifier mismatch")
    require_e2e_contract(artifact, app_root)
    return {
        "schemaVersion": 1,
        "mode": "ipad",
        "artifact": artifact_name,
        "sourceRevision": expected_source_revision,
        "sha256": expected_sha256,
        "platform": "iphoneos",
        "bundleIdentifier": bundle_id,
        "applicationIdentifier": application_identifier,
        "appRoot": app_root,
    }


def verify_candidate(
    directory: Path, mode: str, expected_source_revision: str, expected_sha256: str
) -> dict:
    if mode not in {"simulator", "ipad"}:
        raise ValueError("mode must be simulator or ipad")
    if REVISION.fullmatch(expected_source_revision) is None:
        raise ValueError("expected source revision must be a lowercase 40-character Git SHA")
    if DIGEST.fullmatch(expected_sha256) is None:
        raise ValueError("expected SHA-256 must be a lowercase 64-character digest")

    fedora_payload = find_fedora_manifest(directory)
    if fedora_payload is not None:
        if mode != "ipad":
            raise ValueError("Fedora E2E artifacts are physical-device candidates")
        return verify_fedora_candidate(
            directory, fedora_payload, expected_source_revision, expected_sha256
        )

    payload = load_handoff_verifier().verify_handoff(directory)
    if SAFE_ARTIFACT.fullmatch(str(payload.get("artifact", ""))) is None:
        raise ValueError("integrated-client artifact name is unsafe")
    required_manifest = {
        "schemaVersion": 1,
        "product": "overte-ios-integrated-client",
        "architecture": "arm64",
    }
    for field, expected in required_manifest.items():
        if payload.get(field) != expected:
            raise ValueError(f"integrated-client manifest {field} mismatch")
    if payload.get("sourceRevision") != expected_source_revision:
        raise ValueError("integrated-client manifest source revision mismatch")
    if payload.get("sha256") != expected_sha256:
        raise ValueError("integrated-client manifest SHA-256 mismatch")

    artifact = directory / payload["artifact"]
    if artifact.stat().st_size > MAX_ARCHIVE_BYTES:
        raise ValueError("integrated-client artifact exceeds the runtime size limit")
    signing = payload.get("signing")
    if not isinstance(signing, dict):
        raise ValueError("integrated-client manifest signing metadata is missing")
    if mode == "simulator":
        if artifact.suffix != ".zip" or payload.get("platform") != "iphonesimulator":
            raise ValueError("simulator candidate platform mismatch")
        if payload.get("signed") is not False or payload.get("requiresSigning") is not False:
            raise ValueError("simulator candidate signing metadata mismatch")
    else:
        if artifact.suffix != ".ipa" or payload.get("platform") != "iphoneos":
            raise ValueError("iPad candidate platform mismatch")
        if payload.get("signed") is not True or payload.get("requiresSigning") is not False:
            raise ValueError("iPad candidate must already be signed")
        if signing.get("embeddedProvisioningProfile") is not True:
            raise ValueError("iPad manifest does not confirm an embedded provisioning profile")

    app_root, bundle_id = inspect_archive(artifact, mode)
    application_identifier = signing.get("applicationIdentifier")
    if mode == "ipad":
        if (
            not isinstance(application_identifier, str)
            or not application_identifier.endswith("." + bundle_id)
        ):
            raise ValueError("iPad manifest application identifier mismatch")
        if not isinstance(signing.get("getTaskAllow"), bool):
            raise ValueError("iPad manifest get-task-allow metadata is invalid")
    return {
        "schemaVersion": 1,
        "mode": mode,
        "artifact": payload["artifact"],
        "sourceRevision": expected_source_revision,
        "sha256": expected_sha256,
        "platform": payload["platform"],
        "bundleIdentifier": bundle_id,
        "applicationIdentifier": application_identifier,
        "appRoot": app_root,
    }


def write_github_output(path: Path, plan: dict) -> None:
    fields = {
        "mode": plan["mode"],
        "artifact": plan["artifact"],
        "source_revision": plan["sourceRevision"],
        "sha256": plan["sha256"],
        "platform": plan["platform"],
        "bundle_id": plan["bundleIdentifier"],
        "application_identifier": plan["applicationIdentifier"] or "",
        "app_root": plan["appRoot"],
        "runtime_plan": json.dumps(plan, sort_keys=True, separators=(",", ":")),
    }
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        for key, value in fields.items():
            if "\n" in value or "\r" in value:
                raise ValueError("runtime plan contains an unsafe GitHub output value")
            stream.write(f"{key}={value}\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact_directory", type=Path)
    parser.add_argument("--mode", choices=("simulator", "ipad"), required=True)
    parser.add_argument("--expected-source-revision", required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args()
    try:
        plan = verify_candidate(
            args.artifact_directory,
            args.mode,
            args.expected_source_revision,
            args.expected_sha256,
        )
        if args.github_output is not None:
            write_github_output(args.github_output, plan)
    except (
        OSError,
        RuntimeError,
        ValueError,
        json.JSONDecodeError,
        zipfile.BadZipFile,
    ) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(json.dumps(plan, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
