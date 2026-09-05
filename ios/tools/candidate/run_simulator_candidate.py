#!/usr/bin/env python3
"""Stage the exact verified candidate and optionally run its four simulator cases.

Without --execute this performs offline archive validation only. Real simulator
execution still requires the governing admission; staging is not render proof.
"""
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import plistlib
import stat
import sys
import tempfile
import zipfile

import verify_io001_candidate as verifier
from verify_io001_release import pinned_adapter
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--shared-contract-root", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--online-domain-uuid")
    args = parser.parse_args(argv)
    try:
        adapter = pinned_adapter(args.shared_contract_root)
        binding = verifier.verify_candidate(args.manifest, args.artifact_root, args.expected_source_sha,
            repository=args.repository, shared_evidence_adapter=adapter, require_shared_evidence=True)
        manifest = verifier._load_manifest(args.manifest)
        archive = verifier._safe_artifact_path(args.artifact_root, manifest["artifact"]["relativePath"])
        with tempfile.TemporaryDirectory(prefix="ios-exact-candidate-") as scratch:
            app, bundle = stage_archive(archive, Path(scratch), binding["artifactSha256"])
            verifier._verify_repository_head(args.repository, args.expected_source_sha)
            if args.execute:
                if args.output_dir is None or args.online_domain_uuid is None:
                    raise ValueError("SIMULATOR_PARAMETERS")
                plan = Path(__file__).resolve().parents[2] / "tests/io001-simulator-cases.json"
                simulator.execute_plan(plan, app, bundle, args.output_dir, args.online_domain_uuid)
        print("SIMULATOR_CASES_COMPLETED_NOT_NODE_ACCEPTED" if args.execute else "SIMULATOR_ARCHIVE_VERIFIED_NOT_EXECUTED")
        return 0
    except (OSError, ValueError, zipfile.BadZipFile, plistlib.InvalidFileException):
        print("SIMULATOR_CANDIDATE_REJECTED", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
