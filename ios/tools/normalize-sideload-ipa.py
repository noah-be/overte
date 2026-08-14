#!/usr/bin/env python3
"""Create a conservative, deterministic unsigned IPA for external sideloading."""

# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import argparse
import hashlib
import json
import os
import plistlib
import re
import shutil
import stat
import sys
import tempfile
import zipfile
from pathlib import Path


BUNDLE_ID = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9-]*(?:[.][A-Za-z0-9][A-Za-z0-9-]*)+"
)
DIGEST = re.compile(r"[0-9a-f]{64}")
APP_ROOT = "Payload/Overte.app"
INFO_NAME = f"{APP_ROOT}/Info.plist"
PRIVACY_NAME = f"{APP_ROOT}/PrivacyInfo.xcprivacy"
MAX_ARCHIVE_BYTES = 1024 * 1024 * 1024
MAX_EXPANDED_BYTES = 2 * 1024 * 1024 * 1024
MAX_MEMBERS = 20_000
MAX_PLIST_BYTES = 1024 * 1024
COPY_BUFFER_BYTES = 1024 * 1024
FIXED_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(COPY_BUFFER_BYTES), b""):
            digest.update(block)
    return digest.hexdigest()


def normalized_name(raw_name: str) -> str:
    if not raw_name or "\0" in raw_name or "\\" in raw_name:
        raise ValueError("IPA contains an unsafe ZIP entry")
    if raw_name.startswith("/") or re.match(r"^[A-Za-z]:", raw_name):
        raise ValueError("IPA contains an unsafe ZIP entry")
    name = raw_name[:-1] if raw_name.endswith("/") else raw_name
    if not name or any(part in {"", ".", ".."} for part in name.split("/")):
        raise ValueError("IPA contains an unsafe ZIP entry")
    return name


def is_within_app(name: str) -> bool:
    return name == APP_ROOT or name.startswith(APP_ROOT + "/")


def inspect_source(
    archive: zipfile.ZipFile,
) -> tuple[dict[str, zipfile.ZipInfo], dict, str, str]:
    infos = archive.infolist()
    if not infos or len(infos) > MAX_MEMBERS:
        raise ValueError("IPA has an invalid member count")
    if sum(info.file_size for info in infos) > MAX_EXPANDED_BYTES:
        raise ValueError("IPA expands beyond the safety limit")
    if archive.testzip() is not None:
        raise ValueError("IPA contains a corrupt ZIP entry")

    members: dict[str, zipfile.ZipInfo] = {}
    for info in infos:
        name = normalized_name(info.filename)
        if name in members:
            raise ValueError("IPA contains duplicate ZIP entries")
        if info.flag_bits & 0x1:
            raise ValueError("IPA contains an encrypted ZIP entry")
        file_type = stat.S_IFMT(info.external_attr >> 16)
        if file_type not in {0, stat.S_IFREG, stat.S_IFDIR, stat.S_IFLNK}:
            raise ValueError("IPA contains an unsupported special ZIP entry")
        if name != "Payload" and not is_within_app(name):
            raise ValueError("IPA contains content outside Payload/Overte.app")
        members[name] = info

    info_entry = members.get(INFO_NAME)
    if info_entry is None or info_entry.is_dir() or info_entry.file_size > MAX_PLIST_BYTES:
        raise ValueError("IPA is missing a bounded regular Info.plist")
    if stat.S_ISLNK(info_entry.external_attr >> 16):
        raise ValueError("IPA Info.plist must not be a symlink")
    try:
        metadata = plistlib.loads(archive.read(info_entry))
    except (plistlib.InvalidFileException, ValueError) as error:
        raise ValueError("IPA Info.plist is not a valid property list") from error
    if not isinstance(metadata, dict):
        raise ValueError("IPA Info.plist root must be a dictionary")

    old_bundle_id = metadata.get("CFBundleIdentifier")
    executable = metadata.get("CFBundleExecutable")
    if not isinstance(old_bundle_id, str) or not BUNDLE_ID.fullmatch(old_bundle_id):
        raise ValueError("IPA Info.plist has no valid CFBundleIdentifier")
    if not isinstance(executable, str) or "/" in executable or not executable:
        raise ValueError("IPA Info.plist has no valid CFBundleExecutable")
    executable_name = f"{APP_ROOT}/{executable}"
    executable_entry = members.get(executable_name)
    if executable_entry is None or executable_entry.is_dir():
        raise ValueError("IPA is missing the declared executable")
    executable_mode = executable_entry.external_attr >> 16
    if stat.S_ISLNK(executable_mode) or not executable_mode & 0o111:
        raise ValueError("IPA executable is not a regular executable file")
    if PRIVACY_NAME not in members:
        raise ValueError("IPA is missing PrivacyInfo.xcprivacy")
    if any(
        name == f"{APP_ROOT}/embedded.mobileprovision"
        or name.startswith(f"{APP_ROOT}/_CodeSignature/")
        for name in members
    ):
        raise ValueError("source IPA must be unsigned before normalization")
    return members, metadata, old_bundle_id, executable_name


def output_info(source: zipfile.ZipInfo, filename: str) -> zipfile.ZipInfo:
    result = zipfile.ZipInfo(filename, date_time=FIXED_TIMESTAMP)
    result.create_system = 3
    result.external_attr = source.external_attr
    result.internal_attr = source.internal_attr
    result.compress_type = (
        zipfile.ZIP_STORED
        if source.is_dir() or stat.S_ISLNK(source.external_attr >> 16)
        else zipfile.ZIP_DEFLATED
    )
    result.comment = b""
    result.extra = b""
    result.flag_bits = 0
    return result


def ordered_names(members: dict[str, zipfile.ZipInfo], executable_name: str) -> list[str]:
    preferred = ["Payload", APP_ROOT, INFO_NAME, executable_name, PRIVACY_NAME]
    result = [name for name in preferred if name in members]
    result.extend(sorted(name for name in members if name not in result))
    return result


def normalize(source: Path, output: Path, new_bundle_id: str) -> tuple[str, str]:
    if source.resolve() == output.resolve():
        raise ValueError("input and output IPA paths must differ")
    if not source.is_file() or source.is_symlink():
        raise ValueError("input IPA must be a regular file")
    if source.stat().st_size <= 0 or source.stat().st_size > MAX_ARCHIVE_BYTES:
        raise ValueError("input IPA size is outside the safety limit")
    if output.exists():
        raise ValueError("output IPA already exists")

    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(source, "r") as input_archive:
        members, metadata, old_bundle_id, executable_name = inspect_source(input_archive)
        metadata["CFBundleIdentifier"] = new_bundle_id
        normalized_plist = plistlib.dumps(
            metadata, fmt=plistlib.FMT_XML, sort_keys=True
        )
        with tempfile.NamedTemporaryFile(
            prefix=output.name + ".", suffix=".partial", dir=output.parent, delete=False
        ) as temporary:
            temporary_path = Path(temporary.name)
        try:
            with zipfile.ZipFile(
                temporary_path,
                "w",
                compression=zipfile.ZIP_DEFLATED,
                compresslevel=6,
                allowZip64=True,
            ) as output_archive:
                output_archive.comment = b""
                for name in ordered_names(members, executable_name):
                    source_info = members[name]
                    filename = name + "/" if source_info.is_dir() else name
                    destination_info = output_info(source_info, filename)
                    if name == INFO_NAME:
                        output_archive.writestr(destination_info, normalized_plist)
                        continue
                    if source_info.is_dir():
                        output_archive.writestr(destination_info, b"")
                        continue
                    with input_archive.open(source_info, "r") as source_stream:
                        with output_archive.open(
                            destination_info, "w", force_zip64=True
                        ) as destination_stream:
                            shutil.copyfileobj(
                                source_stream, destination_stream, COPY_BUFFER_BYTES
                            )
            os.replace(temporary_path, output)
        except BaseException:
            temporary_path.unlink(missing_ok=True)
            raise

    with zipfile.ZipFile(output, "r") as output_archive:
        output_members, output_metadata, _, output_executable = inspect_source(
            output_archive
        )
        if output_metadata.get("CFBundleIdentifier") != new_bundle_id:
            raise ValueError("normalized IPA bundle identifier verification failed")
        if output_executable != executable_name:
            raise ValueError("normalized IPA executable identity changed")
        if list(output_members)[:3] != ["Payload", APP_ROOT, INFO_NAME]:
            raise ValueError("normalized IPA does not expose Info.plist early")
    return old_bundle_id, sha256(output)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--bundle-id", required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--manifest", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()
    if not BUNDLE_ID.fullmatch(arguments.bundle_id):
        raise ValueError("requested bundle identifier is invalid")
    if not DIGEST.fullmatch(arguments.expected_sha256):
        raise ValueError("expected SHA-256 is invalid")
    source_digest = sha256(arguments.input)
    if source_digest != arguments.expected_sha256:
        raise ValueError("input IPA SHA-256 does not match the approved value")
    if arguments.manifest.exists():
        raise ValueError("output manifest already exists")
    old_bundle_id, output_digest = normalize(
        arguments.input, arguments.output, arguments.bundle_id
    )
    manifest = {
        "schemaVersion": 1,
        "product": "overte-ios-sideload-normalized",
        "sourceArtifact": arguments.input.name,
        "sourceSha256": source_digest,
        "artifact": arguments.output.name,
        "sha256": output_digest,
        "originalBundleIdentifier": old_bundle_id,
        "bundleIdentifier": arguments.bundle_id,
        "size": arguments.output.stat().st_size,
        "infoPlistFormat": "xml1",
        "signed": False,
        "requiresSigning": True,
    }
    arguments.manifest.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, zipfile.BadZipFile) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1)
