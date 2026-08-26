#!/usr/bin/env python3
"""Fail closed on the opt-in iOS physical-device E2E Info.plist contract."""

# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import argparse
import plistlib
import stat
import sys
import zipfile
from pathlib import Path


CONTRACT_VERSION_KEY = "OverteE2ETestBuildContractVersion"
FILE_SHARING_KEY = "UIFileSharingEnabled"
E2E_BINARY_MARKER = b"Rejected iOS E2E results path outside Documents"
MAX_EXECUTABLE_BYTES = 2 * 1024 * 1024 * 1024
MAX_PLIST_BYTES = 4 * 1024 * 1024


def validate(info: object, expected: str) -> None:
    if not isinstance(info, dict):
        raise ValueError("Info.plist root is not a dictionary")
    version = info.get(CONTRACT_VERSION_KEY)
    sharing = info.get(FILE_SHARING_KEY)
    if expected == "enabled":
        if version != 1 or isinstance(version, bool):
            raise ValueError("E2E test-build contract version must be integer 1")
        if sharing is not True:
            raise ValueError("E2E test builds must enable Files app result export")
    elif CONTRACT_VERSION_KEY in info or FILE_SHARING_KEY in info:
        raise ValueError("normal iOS builds must not contain E2E test-build markers")


def contains_marker(stream, marker: bytes, size: int) -> bool:
    if size <= 0 or size > MAX_EXECUTABLE_BYTES:
        raise ValueError("packaged Overte executable size is invalid")
    overlap = b""
    remaining = size
    while remaining:
        chunk = stream.read(min(1024 * 1024, remaining))
        if not chunk:
            raise ValueError("packaged Overte executable is truncated")
        remaining -= len(chunk)
        candidate = overlap + chunk
        if marker in candidate:
            return True
        overlap = candidate[-(len(marker) - 1):]
    return False


def validate_archive(archive_path: Path, app_root: str, expected: str) -> None:
    if app_root not in {"Overte.app", "Payload/Overte.app"}:
        raise ValueError("archive root is not an audited Overte application path")
    with zipfile.ZipFile(archive_path) as archive:
        names = [entry.filename.rstrip("/") for entry in archive.infolist()]
        info_name = f"{app_root}/Info.plist"
        executable_name = f"{app_root}/Overte"
        if names.count(info_name) != 1 or names.count(executable_name) != 1:
            raise ValueError("archive must contain one Overte Info.plist and executable")
        info_entry = archive.getinfo(info_name)
        executable_entry = archive.getinfo(executable_name)
        if (
            info_entry.is_dir()
            or executable_entry.is_dir()
            or stat.S_IFMT(info_entry.external_attr >> 16) not in {0, stat.S_IFREG}
            or stat.S_IFMT(executable_entry.external_attr >> 16)
            not in {0, stat.S_IFREG}
            or info_entry.flag_bits & 0x1
            or executable_entry.flag_bits & 0x1
            or info_entry.file_size <= 0
            or info_entry.file_size > MAX_PLIST_BYTES
        ):
            raise ValueError("archive E2E contract members must be regular files")
        try:
            info = plistlib.loads(archive.read(info_entry))
        except plistlib.InvalidFileException as error:
            raise ValueError("packaged Overte Info.plist is invalid") from error
        validate(info, expected)
        with archive.open(executable_entry) as executable:
            marker_present = contains_marker(
                executable, E2E_BINARY_MARKER, executable_entry.file_size
            )
    if expected == "enabled" and not marker_present:
        raise ValueError("E2E package does not contain its opt-in runtime boundary")
    if expected == "disabled" and marker_present:
        raise ValueError("normal iOS package contains the E2E runtime boundary")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--expected", choices=("enabled", "disabled"), required=True)
    parser.add_argument("--archive-root", choices=("Overte.app", "Payload/Overte.app"))
    args = parser.parse_args()
    try:
        if args.archive_root is None:
            with args.input.open("rb") as stream:
                info = plistlib.load(stream)
            validate(info, args.expected)
        else:
            validate_archive(args.input, args.archive_root, args.expected)
    except (OSError, ValueError, zipfile.BadZipFile, plistlib.InvalidFileException) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(f"PASS iOS E2E test-build contract is {args.expected}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
