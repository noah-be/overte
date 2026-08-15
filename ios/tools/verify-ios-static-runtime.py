#!/usr/bin/env python3
"""Reject non-system Mach-O runtime dependencies in an iOS app executable."""

# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import argparse
import json
import plistlib
import struct
import sys
from pathlib import Path
from typing import BinaryIO


MACHO_64_MAGIC = 0xFEEDFACF
CPU_TYPE_ARM64 = 0x0100000C
MAX_COMMANDS = 4096
MAX_COMMAND_BYTES = 4 * 1024 * 1024
LC_LOAD_DYLIB = 0xC
LC_LAZY_LOAD_DYLIB = 0x20
LC_LOAD_WEAK_DYLIB = 0x80000018
LC_REEXPORT_DYLIB = 0x8000001F
LC_LOAD_UPWARD_DYLIB = 0x80000023
LC_RPATH = 0x8000001C
DYLIB_COMMANDS = {
    LC_LOAD_DYLIB,
    LC_LAZY_LOAD_DYLIB,
    LC_LOAD_WEAK_DYLIB,
    LC_REEXPORT_DYLIB,
    LC_LOAD_UPWARD_DYLIB,
}
ALLOWED_DEPENDENCY_PREFIXES = ("/System/Library/Frameworks/", "/usr/lib/")
ALLOWED_RPATHS = {"@executable_path/Frameworks", "@loader_path/Frameworks"}
FORBIDDEN_IOS_UI_MARKERS = (
    b"Choose a display mode to start with:",
)
SCAN_CHUNK_BYTES = 1024 * 1024


def command_string(commands: bytes, offset: int, size: int) -> str:
    if size < 12:
        raise ValueError("Mach-O contains a truncated path command")
    string_offset = struct.unpack_from("<I", commands, offset + 8)[0]
    if string_offset < 12 or string_offset >= size:
        raise ValueError("Mach-O contains an invalid path offset")
    raw = commands[offset + string_offset : offset + size]
    terminator = raw.find(b"\0")
    if terminator < 0:
        raise ValueError("Mach-O contains an unterminated load path")
    try:
        value = raw[:terminator].decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("Mach-O contains a non-UTF-8 load path") from error
    if not value or "\n" in value or "\r" in value:
        raise ValueError("Mach-O contains an unsafe empty or multiline load path")
    return value


def audit_macho_parts(header: bytes, commands: bytes) -> dict:
    if len(header) != 32:
        raise ValueError("executable has no complete Mach-O header")
    magic, cpu_type, _subtype, _filetype, count, size, _flags, _reserved = struct.unpack(
        "<IiiIIIII", header
    )
    if magic != MACHO_64_MAGIC or cpu_type != CPU_TYPE_ARM64:
        raise ValueError("executable is not a thin arm64 Mach-O")
    if count > MAX_COMMANDS or size > MAX_COMMAND_BYTES:
        raise ValueError("Mach-O load-command table is unreasonable")
    if len(commands) != size:
        raise ValueError("Mach-O load-command table is truncated")

    dependencies: list[str] = []
    rpaths: list[str] = []
    offset = 0
    for _ in range(count):
        if offset + 8 > len(commands):
            raise ValueError("Mach-O load-command table is malformed")
        command, command_size = struct.unpack_from("<II", commands, offset)
        if command_size < 8 or offset + command_size > len(commands):
            raise ValueError("Mach-O load-command table is malformed")
        if command in DYLIB_COMMANDS:
            dependencies.append(command_string(commands, offset, command_size))
        elif command == LC_RPATH:
            rpaths.append(command_string(commands, offset, command_size))
        offset += command_size
    if offset != len(commands):
        raise ValueError("Mach-O load-command size does not match its header")

    forbidden_dependencies = sorted(
        dependency
        for dependency in dependencies
        if not dependency.startswith(ALLOWED_DEPENDENCY_PREFIXES)
    )
    if forbidden_dependencies:
        raise ValueError(
            "executable has non-system runtime dependencies: "
            + ", ".join(forbidden_dependencies)
        )
    forbidden_rpaths = sorted(rpath for rpath in rpaths if rpath not in ALLOWED_RPATHS)
    if forbidden_rpaths:
        raise ValueError(
            "executable has unsafe or build-local runtime search paths: "
            + ", ".join(forbidden_rpaths)
        )
    return {"dependencies": dependencies, "rpaths": rpaths}


def audit_ios_ui_markers(stream: BinaryIO) -> None:
    """Reject an iOS executable that still contains a desktop-only startup dialog."""
    overlap = max(len(marker) for marker in FORBIDDEN_IOS_UI_MARKERS) - 1
    previous = b""
    while True:
        chunk = stream.read(SCAN_CHUNK_BYTES)
        if not chunk:
            return
        searchable = previous + chunk
        if any(marker in searchable for marker in FORBIDDEN_IOS_UI_MARKERS):
            raise ValueError("executable contains the legacy desktop display-mode selector")
        previous = searchable[-overlap:] if overlap else b""


def audit_macho_stream(stream: BinaryIO) -> dict:
    header = stream.read(32)
    if len(header) != 32:
        raise ValueError("executable has no complete Mach-O header")
    command_size = struct.unpack_from("<I", header, 20)[0]
    if command_size > MAX_COMMAND_BYTES:
        raise ValueError("Mach-O load-command table is unreasonable")
    report = audit_macho_parts(header, stream.read(command_size))
    audit_ios_ui_markers(stream)
    return report


def audit_app(app: Path) -> dict:
    if not app.is_dir() or app.suffix != ".app":
        raise ValueError("path is not an iOS application bundle")
    info_path = app / "Info.plist"
    with info_path.open("rb") as stream:
        info = plistlib.load(stream)
    executable_name = info.get("CFBundleExecutable") if isinstance(info, dict) else None
    if not isinstance(executable_name, str) or Path(executable_name).name != executable_name:
        raise ValueError("Info.plist has no safe CFBundleExecutable")
    executable = app / executable_name
    with executable.open("rb") as stream:
        report = audit_macho_stream(stream)
    return {
        "schemaVersion": 1,
        "bundle": app.name,
        "executable": executable_name,
        "runtimeDependencyCount": len(report["dependencies"]),
        "runtimeDependencies": report["dependencies"],
        "runtimeSearchPaths": report["rpaths"],
        "thirdPartyRuntimeDependencies": [],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("app", type=Path)
    args = parser.parse_args()
    try:
        report = audit_app(args.app)
    except (OSError, ValueError, plistlib.InvalidFileException) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
