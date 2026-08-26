#!/usr/bin/env python3
"""Create the exact private IPA+manifest ZIP that is encrypted for the Fedora lab."""

# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
import sys
import zipfile
from pathlib import Path


CONTRACT = "overte-ios-fedora-e2e-artifact-v1"
SAFE_IPA = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,191}[.]ipa")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_regular_file(path: Path, description: str) -> None:
    metadata = path.lstat()
    if path.is_symlink() or not stat.S_ISREG(metadata.st_mode) or metadata.st_size <= 0:
        raise ValueError(f"{description} must be a non-empty regular file")


def create_inner_zip(output: Path, ipa: Path, manifest: Path) -> list[str]:
    if output.exists() or output.is_symlink() or output.suffix != ".zip":
        raise ValueError("inner ZIP output must be a new .zip path")
    require_regular_file(ipa, "signed IPA")
    require_regular_file(manifest, "artifact manifest")
    if SAFE_IPA.fullmatch(ipa.name) is None:
        raise ValueError("signed IPA basename is invalid")
    if manifest.name != f"{ipa.stem}.manifest.json":
        raise ValueError("manifest basename does not match the signed IPA")
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    if payload.get("contract") != CONTRACT:
        raise ValueError("manifest contract mismatch")
    artifact = payload.get("artifact")
    if not isinstance(artifact, dict) or artifact.get("name") != ipa.name:
        raise ValueError("manifest artifact name does not select the signed IPA")
    if artifact.get("size") != ipa.stat().st_size or artifact.get("sha256") != sha256_file(ipa):
        raise ValueError("manifest digest or size does not match the signed IPA")
    names = [ipa.name, manifest.name]
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_STORED) as archive:
        archive.write(ipa, arcname=ipa.name)
        archive.write(manifest, arcname=manifest.name)
    output.chmod(0o600)
    with zipfile.ZipFile(output) as archive:
        if archive.namelist() != names or archive.testzip() is not None:
            raise ValueError("inner ZIP failed exact structure verification")
        if any(info.compress_type != zipfile.ZIP_STORED for info in archive.infolist()):
            raise ValueError("inner ZIP unexpectedly recompressed a signed artifact")
    return names


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("ipa", type=Path)
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    try:
        names = create_inner_zip(args.output, args.ipa, args.manifest)
    except (OSError, ValueError, json.JSONDecodeError, zipfile.BadZipFile) as error:
        print(f"error: private age handoff rejected: {error}", file=sys.stderr)
        return 1
    print(json.dumps({"schemaVersion": 1, "files": names}, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
