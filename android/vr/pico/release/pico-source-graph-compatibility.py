#!/usr/bin/env python3
"""Fail-closed boundary for an explicitly supplied Pico source graph."""

from __future__ import annotations

import argparse
from pathlib import Path
import os
import re
import sys


LEGACY_PAYLOAD_NAMES = {
    ".prebuilt-runtime",
    "pico4-node-conan.tgz",
    "pico4-qt-conan.tgz",
    "pico4-runtime.tgz",
}
OPENSSL_11_PATH = re.compile(
    r"(?:^|/)(?:lib(?:ssl|crypto)\.so\.1\.1(?:\.|$)|openssl[-_/]?1[._-]1(?:[._-]|$))",
    re.IGNORECASE,
)
FORBIDDEN_ADAPTER_PATTERNS = (
    (re.compile(r"https?://", re.IGNORECASE), "network URL"),
    (re.compile(r"\b(?:curl|wget)\b", re.IGNORECASE), "network downloader"),
    (re.compile(r"\bgit\s+clone\b", re.IGNORECASE), "Git network acquisition"),
    (re.compile(r"\bconan(?:\s|$)", re.IGNORECASE), "Conan execution"),
    (re.compile(r"--build(?:=|\s+)missing", re.IGNORECASE), "--build=missing"),
    (re.compile(r"(?:-pr:[hb]|--profile(?::[hb])?)\s*[=\"']?default\b", re.IGNORECASE),
     "default profile"),
    (re.compile(r"artifactory\.overte\.org", re.IGNORECASE), "Overte Artifactory"),
    (re.compile(r"pico4-(?:deps-v1|node-conan|qt-conan|runtime)", re.IGNORECASE),
     "historical Pico prebuilt"),
)
MAX_ADAPTER_BYTES = 1024 * 1024


def fail(message: str) -> None:
    print(f"PICO_SOURCE_GRAPH_COMPATIBILITY=FAIL\t{message}", file=sys.stderr)
    raise SystemExit(2)


def canonical_absolute_directory(value: str, label: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        fail(f"{label} must be absolute")
    try:
        resolved = path.resolve(strict=True)
    except OSError as error:
        fail(f"{label} is unavailable: {error.strerror or error}")
    if resolved != path or not resolved.is_dir():
        fail(f"{label} must be an existing canonical directory")
    return resolved


def validate_graph_root(root: Path) -> int:
    entries = 0
    for entry in root.rglob("*"):
        entries += 1
        try:
            resolved = entry.resolve(strict=True)
            resolved.relative_to(root)
        except (OSError, ValueError):
            fail(f"graph entry escapes its root: {entry.relative_to(root)}")
        relative = entry.relative_to(root).as_posix()
        if entry.name.lower() in LEGACY_PAYLOAD_NAMES:
            fail(f"historical prebuilt payload is forbidden: {relative}")
        if OPENSSL_11_PATH.search(relative):
            fail(f"OpenSSL 1.1 payload is forbidden: {relative}")
    return entries


def validate_adapter(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        fail("PICO_SHARED_GRAPH_ADAPTER must be absolute")
    try:
        resolved = path.resolve(strict=True)
    except OSError as error:
        fail(f"PICO_SHARED_GRAPH_ADAPTER is unavailable: {error.strerror or error}")
    if resolved != path or not resolved.is_file() or not os.access(resolved, os.X_OK):
        fail("PICO_SHARED_GRAPH_ADAPTER must be a canonical executable file")
    if resolved.stat().st_size > MAX_ADAPTER_BYTES:
        fail("PICO_SHARED_GRAPH_ADAPTER exceeds the 1 MiB inspection limit")
    try:
        source = resolved.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        fail("PICO_SHARED_GRAPH_ADAPTER must be inspectable UTF-8 source")
    for pattern, label in FORBIDDEN_ADAPTER_PATTERNS:
        if pattern.search(source):
            fail(f"adapter contains forbidden {label}")
    return resolved


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph-root", required=True)
    parser.add_argument("--adapter", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root = canonical_absolute_directory(args.graph_root, "PICO_SOURCE_GRAPH_ROOT")
    entries = validate_graph_root(root)
    validate_adapter(args.adapter)
    print(f"PICO_SOURCE_GRAPH_COMPATIBILITY=PASS\tentries={entries}")


if __name__ == "__main__":
    main()
