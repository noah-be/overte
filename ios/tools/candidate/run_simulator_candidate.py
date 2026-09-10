#!/usr/bin/env python3
"""Stage the exact verified candidate and optionally run its four simulator cases.

Without --execute this performs offline archive validation only. Real simulator
execution still requires the governing admission; staging is not render proof.
"""
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0
import hashlib
import os
from pathlib import Path, PurePosixPath
import plistlib
import stat
import sys
import zipfile

import verify_io001_candidate as verifier
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tests"))
import io001_simulator_plan as simulator

MAX_ARCHIVE_MEMBERS = 100000
MAX_UNPACKED_BYTES = 8 * 1024 * 1024 * 1024
MAX_FILE_BYTES = 4 * 1024 * 1024 * 1024


def stage_archive(archive: Path, destination: Path, expected_digest: str | None = None) -> tuple[Path, str]:
    if any(destination.iterdir()):
        raise ValueError("STAGING_NOT_EMPTY")
    if archive.is_symlink() or not archive.is_file():
        raise ValueError("ARCHIVE_NOT_REGULAR")
    # Snapshot the exact bytes into private staging before extraction. A caller
    # replacing the producer's archive after verification cannot change this app.
    snapshot = destination / "candidate-bytes.zip"
    digest, copied_bytes = hashlib.sha256(), 0
    with archive.open("rb") as source, snapshot.open("xb") as output:
        while chunk := source.read(1024 * 1024):
            copied_bytes += len(chunk)
            if copied_bytes > verifier.MAX_ARTIFACT_BYTES:
                raise ValueError("ARCHIVE_BYTE_LIMIT")
            digest.update(chunk)
            output.write(chunk)
    if expected_digest is not None and digest.hexdigest() != expected_digest:
        raise ValueError("ARCHIVE_BINDING_CHANGED")
    seen, total = set(), 0
    with zipfile.ZipFile(snapshot) as package:
        members = package.infolist()
        if not 1 <= len(members) <= MAX_ARCHIVE_MEMBERS:
            raise ValueError("ARCHIVE_MEMBER_LIMIT")
        for item in members:
            name = item.filename
            path = PurePosixPath(name)
            if not name or path.is_absolute() or ".." in path.parts or "\\" in name or "\0" in name:
                raise ValueError("ARCHIVE_PATH")
            if path.parts[0] == "__MACOSX":
                continue  # ditto resource-fork metadata is not installed app content
            if path.parts[0] != "Overte.app" or len(path.parts) == 1 and not item.is_dir():
                raise ValueError("ARCHIVE_PRODUCT")
            # APFS defaults to case-insensitive filenames. Reject aliases before
            # extraction on every host, including case-sensitive test machines.
            canonical = str(path).casefold()
            if canonical in seen:
                raise ValueError("ARCHIVE_DUPLICATE")
            seen.add(canonical)
            mode = item.external_attr >> 16
            kind = stat.S_IFMT(mode)
            if kind not in (0, stat.S_IFREG, stat.S_IFDIR) or item.flag_bits & 1:
                raise ValueError("ARCHIVE_SPECIAL_FILE")
            if not 0 <= item.file_size <= MAX_FILE_BYTES:
                raise ValueError("ARCHIVE_FILE_LIMIT")
            total += item.file_size
            if total > MAX_UNPACKED_BYTES:
                raise ValueError("ARCHIVE_TOTAL_LIMIT")
            target = destination.joinpath(*path.parts)
            if item.is_dir():
                target.mkdir(parents=True, exist_ok=True, mode=0o700)
                continue
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            copied = 0
            with package.open(item) as source, target.open("xb") as output:
                while chunk := source.read(1024 * 1024):
                    copied += len(chunk)
                    if copied > item.file_size:
                        raise ValueError("ARCHIVE_SIZE_MISMATCH")
                    output.write(chunk)
            if copied != item.file_size:
                raise ValueError("ARCHIVE_SIZE_MISMATCH")
            target.chmod(0o600 | (mode & 0o111))
    app = destination / "Overte.app"
    info_path = app / "Info.plist"
    if not info_path.is_file() or info_path.stat().st_size > 262144:
        raise ValueError("APP_INFO")
    info = plistlib.loads(info_path.read_bytes())
    if not isinstance(info, dict) or info.get("CFBundlePackageType") != "APPL" or \
            info.get("CFBundleSupportedPlatforms") != ["iPhoneSimulator"]:
        raise ValueError("APP_NOT_SIMULATOR")
    executable = info.get("CFBundleExecutable")
    if not isinstance(executable, str) or not executable or "/" in executable or "\\" in executable or \
            executable in (".", "..") or not (app / executable).is_file() or not os.access(app / executable, os.X_OK):
        raise ValueError("APP_EXECUTABLE")
    bundle = info.get("CFBundleIdentifier")
    if not isinstance(bundle, str) or simulator.BUNDLE_ID.fullmatch(bundle) is None:
        raise ValueError("APP_BUNDLE_ID")
    return app, bundle


def main(argv: list[str]) -> int:
    # The simulator consumer uses the same required SH-002/009 binding as the
    # candidate handoff. --execute remains an explicit, separately authorized
    # operation; without it this entry only stages the verified archive.
    from verify_candidate_handoff import main as verify_handoff
    return verify_handoff([*argv, "--stage-simulator"])


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
