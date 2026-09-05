#!/usr/bin/env python3
"""Verify an IO-001 candidate with the pinned, required Shared evidence adapter.

The General-owned release stays external; no Shared schema is copied into iOS.
Run this entry point for candidate handoff. The lower-level verifier also supports
preparation-only diagnostics, which do not establish Shared binding.
"""
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
import argparse
import hashlib
import os
from pathlib import Path, PurePosixPath
import sys

try:
    from . import verify_io001_candidate as candidate
except ImportError:
    import verify_io001_candidate as candidate

CONTRACT = "sh002-ios-evidence/v001"
MANIFEST_SHA256 = "82aeff4ed3cfb35c21a5ef193593c0f753482026d552ab9771b3f4ca42d5e182"
ADAPTER = "ios/ci/evidence/verify-shared-evidence.py"


def pinned_adapter(root: Path) -> Path:
    root = root.absolute()
    if any(p.is_symlink() for p in (root, *root.parents)) or not root.is_dir():
        raise ValueError("SHARED_CONTRACT_ROOT")
    manifest = root / "SHA256SUMS"
    if manifest.is_symlink() or not manifest.is_file():
        raise ValueError("SHARED_MANIFEST_MISSING")
    with manifest.open("rb") as stream:
        raw = stream.read(16385)
    if len(raw) > 16384 or hashlib.sha256(raw).hexdigest() != MANIFEST_SHA256:
        raise ValueError("SHARED_MANIFEST_PIN")
    seen = set()
    for line in raw.decode("ascii").splitlines():
        expected, name = line.split("  ", 1)
        relative = PurePosixPath(name)
        if relative.is_absolute() or ".." in relative.parts or name in seen:
            raise ValueError("SHARED_MANIFEST_PATH")
        seen.add(name)
        file = root.joinpath(*relative.parts)
        if any(p.is_symlink() for p in (file, *file.parents)) or not file.is_file():
            raise ValueError("SHARED_SOURCE_MISSING")
        with file.open("rb") as stream:
            contents = stream.read(1048577)
        if len(contents) > 1048576 or hashlib.sha256(contents).hexdigest() != expected:
            raise ValueError("SHARED_SOURCE_DIGEST")
    adapter = root / ADAPTER
    if "./" + ADAPTER not in seen or not os.access(adapter, os.X_OK):
        raise ValueError("SHARED_ADAPTER_NOT_EXECUTABLE")
    return adapter


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--shared-contract-root", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        adapter = pinned_adapter(args.shared_contract_root)
    except (OSError, ValueError, UnicodeError):
        print("candidate verification failed: pinned Shared release unavailable or changed", file=sys.stderr)
        return 1
    return candidate.main([
        str(args.manifest), "--artifact-root", str(args.artifact_root),
        "--repository", str(args.repository), "--expected-source-sha", args.expected_source_sha,
        "--shared-evidence-adapter", str(adapter), "--require-shared-evidence",
    ])


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
