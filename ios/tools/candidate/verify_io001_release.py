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
from pathlib import Path
import sys

try:
    from . import verify_io001_candidate as candidate
    from .shared_release import verify_release
except ImportError:
    import verify_io001_candidate as candidate
    from shared_release import verify_release

CONTRACT = "sh002-ios-evidence/v002"
MANIFEST_SHA256 = "6eace7138cc76534b64ce57176fe85a75555d00143ac6c901c400fde78ca36ec"
ADAPTER = "ios/ci/evidence/verify-shared-evidence.py"


def pinned_adapter(root: Path) -> Path:
    return verify_release(root, MANIFEST_SHA256, ADAPTER)


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
