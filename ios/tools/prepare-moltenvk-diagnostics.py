#!/usr/bin/env python3
"""Validate and sanitize a bounded MoltenVK shader-dump directory."""

# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import stat
import struct
import sys
import tempfile


MAX_FILES = 128
MAX_FILE_BYTES = 4 * 1024 * 1024
MAX_TOTAL_BYTES = 64 * 1024 * 1024
SPIRV_MAGIC = 0x07230203
FNV1A_OFFSET = 1469598103934665603
FNV1A_PRIME = 1099511628211
SHADER_NAME = re.compile(
    r"shader(?:-(?:vs|tcs|tes|fs|gs|ts|ms|cs))?-[0-9a-f]{16}[.](?:metal|spv)"
)
PIPELINE_NAME = re.compile(r"pipeline(?:-tess)?-[0-9a-f]{16}[.]txt")
LOCAL_PATH = re.compile(r"(?<![A-Za-z0-9_])(/(?:Users|home))/[^/\s]+")
FORBIDDEN_BINARY_MARKERS = (
    b"authorization:",
    b"http://",
    b"https://",
    b"password:",
    b"password=",
    b"secret:",
    b"secret=",
    b"token:",
    b"token=",
    b"-----begin ",
    b"/users/",
    b"/home/",
)


def load_sanitizer():
    sanitizer_path = Path(__file__).with_name("sanitize-ci-log.py")
    spec = importlib.util.spec_from_file_location("overte_ci_log_sanitizer", sanitizer_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("CI log sanitizer is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def is_allowed_name(name: str) -> bool:
    return SHADER_NAME.fullmatch(name) is not None or PIPELINE_NAME.fullmatch(name) is not None


def diagnostic_fingerprint(payload: bytes) -> int:
    fingerprint = FNV1A_OFFSET
    for byte in payload:
        fingerprint ^= byte
        fingerprint = (fingerprint * FNV1A_PRIME) & 0xFFFFFFFFFFFFFFFF
    return fingerprint


def prepare(source: Path, destination: Path) -> int:
    if source.is_symlink() or not source.is_dir():
        raise ValueError("MoltenVK source must be a real directory")
    if destination.exists() or destination.is_symlink():
        raise ValueError("MoltenVK diagnostic destination must not exist")

    sanitizer = load_sanitizer()
    selected: list[tuple[str, bytes, dict[str, object]]] = []
    rejected_unexpected = 0
    total = 0
    for entry in sorted(source.iterdir(), key=lambda candidate: candidate.name):
        if not is_allowed_name(entry.name):
            rejected_unexpected += 1
            continue
        entry_stat = entry.lstat()
        if not stat.S_ISREG(entry_stat.st_mode):
            raise ValueError("MoltenVK dump contains a non-regular diagnostic")
        if entry_stat.st_size > MAX_FILE_BYTES:
            raise ValueError("MoltenVK diagnostic exceeds the per-file limit")
        total += entry_stat.st_size
        if total > MAX_TOTAL_BYTES:
            raise ValueError("MoltenVK diagnostics exceed the total-size limit")
        if len(selected) >= MAX_FILES:
            raise ValueError("MoltenVK diagnostics exceed the file-count limit")

        payload = entry.read_bytes()
        if len(payload) != entry_stat.st_size:
            raise ValueError("MoltenVK diagnostic changed while being read")
        if entry.suffix == ".spv":
            if len(payload) < 20 or len(payload) % 4 != 0:
                raise ValueError("MoltenVK SPIR-V diagnostic has an invalid size")
            if struct.unpack_from("<I", payload)[0] != SPIRV_MAGIC:
                raise ValueError("MoltenVK SPIR-V diagnostic has an invalid magic word")
            lowered = payload.lower()
            if any(marker in lowered for marker in FORBIDDEN_BINARY_MARKERS):
                raise ValueError("MoltenVK SPIR-V diagnostic contains private text")
            output = payload
        else:
            sanitized = payload.decode("utf-8", errors="strict")
            for pattern in sanitizer.PATTERNS:
                if pattern is sanitizer.PATTERNS[0]:
                    sanitized = pattern.sub(r"\1\2[REDACTED]", sanitized)
                elif pattern is sanitizer.PATTERNS[1]:
                    sanitized = pattern.sub(r"\1[REDACTED]@", sanitized)
                else:
                    sanitized = pattern.sub("[REDACTED PRIVATE KEY]", sanitized)
            output = LOCAL_PATH.sub(r"\1/[REDACTED]", sanitized).encode("utf-8")
        metadata: dict[str, object] = {
            "name": entry.name,
            "bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
            "kind": entry.suffix.removeprefix("."),
        }
        if entry.suffix == ".spv":
            metadata["overteDiagnosticFingerprint"] = diagnostic_fingerprint(payload)
        selected.append((entry.name, output, metadata))

    if not selected:
        return 0

    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.", dir=str(destination.parent))
    )
    try:
        for name, payload, _metadata in selected:
            target = staging / name
            target.write_bytes(payload)
            target.chmod(0o600)
        manifest = {
            "schemaVersion": 1,
            "files": [metadata for _name, _payload, metadata in selected],
            "rejected": (
                [{"reason": "unexpected-name", "count": rejected_unexpected}]
                if rejected_unexpected
                else []
            ),
        }
        manifest_path = staging / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        manifest_path.chmod(0o600)
        os.replace(staging, destination)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return len(selected)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    try:
        count = prepare(args.source, args.destination)
    except (OSError, ValueError, RuntimeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(f"prepared_moltenvk_diagnostics={count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
