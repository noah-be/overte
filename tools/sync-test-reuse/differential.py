#!/usr/bin/env python3
"""Run trusted, hardware-free differential contracts against a candidate tree."""

from __future__ import annotations

from pathlib import Path
import argparse
import json
import re
import subprocess
import sys


PROFILES = {
    "documentation": (),
    "android-family": ("android", "interface", "libraries"),
    "android-phone": ("android/phone", "android/common"),
    "android-vr": ("android/vr", "android/common"),
    "android-pico": ("android/vr/pico", "android/vr", "android/common"),
    "apple-family": ("ios", "interface", "libraries"),
    "apple-ios": ("ios", "interface"),
    "linux-desktop": ("cmake", "interface", "libraries"),
    "windows-desktop": ("cmake", "interface", "libraries"),
}


def safe_candidate(root: Path, relative: str) -> Path:
    candidate = root / relative
    current = root
    for part in Path(relative).parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"candidate path uses a symbolic link: {relative}")
    try:
        candidate.resolve().relative_to(root)
    except ValueError as error:
        raise ValueError(f"candidate path escapes the checkout: {relative}") from error
    return candidate


def ensure_no_conflict_markers(root: Path, paths: list[str]) -> None:
    markers = re.compile(rb"^(<<<<<<< |=======\r?$|>>>>>>> )", re.MULTILINE)
    for relative in paths:
        candidate = safe_candidate(root, relative)
        if not candidate.is_file() or candidate.stat().st_size > 2_000_000:
            continue
        if markers.search(candidate.read_bytes()):
            raise ValueError(f"unresolved merge marker in {relative}")


def validate_json(root: Path, paths: list[str]) -> None:
    for relative in paths:
        if relative.endswith(".json"):
            candidate = safe_candidate(root, relative)
            if candidate.stat().st_size > 2_000_000:
                raise ValueError(f"JSON differential input is too large: {relative}")
            json.loads(candidate.read_text(encoding="utf-8"))


def required_roots(root: Path, profile: str, changed: list[str]) -> None:
    if profile not in PROFILES:
        raise ValueError(f"unknown differential profile: {profile}")
    if profile == "documentation":
        if any(not (path.endswith(".md") or path.startswith("docs/")) for path in changed):
            raise ValueError("documentation profile received a non-documentation change")
        return
    for relative in PROFILES[profile]:
        if not safe_candidate(root, relative).exists():
            raise ValueError(f"required candidate path is missing: {relative}")


def syntax_contracts(root: Path, paths: list[str]) -> None:
    python_files = [str(safe_candidate(root, path)) for path in paths if path.endswith(".py")]
    if python_files:
        subprocess.run(
            [sys.executable, "-m", "py_compile", *python_files], check=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--changed-paths", type=Path, required=True)
    args = parser.parse_args()
    root = args.candidate.resolve()
    changed = [line for line in args.changed_paths.read_text(encoding="utf-8").splitlines() if line]
    try:
        for relative in changed:
            if relative.startswith("/") or ".." in Path(relative).parts:
                raise ValueError(f"unsafe changed path: {relative}")
        ensure_no_conflict_markers(root, changed)
        validate_json(root, changed)
        required_roots(root, args.profile, changed)
        syntax_contracts(root, changed)
    except (OSError, ValueError, json.JSONDecodeError, subprocess.CalledProcessError) as error:
        print(f"differential error: {error}", file=sys.stderr)
        return 2
    print(f"differential={args.profile} paths={len(changed)} PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
