#!/usr/bin/env python3
"""Run trusted, hardware-free differential contracts against a candidate tree."""

from __future__ import annotations

from dataclasses import dataclass
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
}


@dataclass(frozen=True)
class ChangedFile:
    filename: str
    status: str
    previous_filename: str | None = None


def load_changes(path: Path, *, structured: bool) -> list[ChangedFile]:
    source = path.read_text(encoding="utf-8")
    if not structured:
        # A filename alone never authorizes ignoring a missing candidate file.
        return [ChangedFile(line, "modified") for line in source.splitlines() if line]
    documents = json.loads(source)
    if not isinstance(documents, list):
        raise ValueError("changed files must be a JSON array")
    changes = []
    seen = set()
    for item in documents:
        if not isinstance(item, dict):
            raise ValueError("changed file must be an object")
        filename = item.get("filename")
        status = item.get("status")
        previous = item.get("previous_filename")
        if not isinstance(filename, str) or not filename:
            raise ValueError("changed file has no filename")
        if not isinstance(status, str) or status not in {
            "added", "modified", "removed", "renamed", "copied", "changed",
        }:
            raise ValueError(f"invalid changed file status for {filename}: {status!r}")
        if status == "renamed" and (not isinstance(previous, str) or not previous):
            raise ValueError(f"renamed file has no previous filename: {filename}")
        if previous is not None and (
            status not in {"renamed", "copied"} or not isinstance(previous, str) or not previous
        ):
            raise ValueError(f"invalid previous filename for {filename}")
        if filename in seen:
            raise ValueError(f"duplicate changed filename: {filename}")
        seen.add(filename)
        changes.append(ChangedFile(filename, status, previous))
    return changes


def safe_candidate(root: Path, relative: str) -> Path:
    if not relative or relative == "." or Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise ValueError(f"unsafe changed path: {relative}")
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


def current_paths(root: Path, changes: list[ChangedFile]) -> list[str]:
    paths = []
    for change in changes:
        candidate = safe_candidate(root, change.filename)
        if change.previous_filename is not None:
            safe_candidate(root, change.previous_filename)
        if change.status == "removed":
            if candidate.exists():
                raise ValueError(f"removed candidate path is still present: {change.filename}")
        else:
            if not candidate.exists():
                raise ValueError(f"changed candidate path is missing: {change.filename}")
            paths.append(change.filename)
    return paths


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
        if any(not path.endswith(".md") for path in changed):
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
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--changed-files", type=Path, help="Trusted PR file objects, including status, as a JSON array")
    inputs.add_argument("--changed-paths", type=Path, help="Legacy filename list; all paths must exist in the candidate")
    args = parser.parse_args()
    root = args.candidate.resolve()
    try:
        changes = load_changes(args.changed_files or args.changed_paths, structured=args.changed_files is not None)
        current = current_paths(root, changes)
        changed = [path for change in changes for path in (change.filename, change.previous_filename) if path is not None]
        ensure_no_conflict_markers(root, current)
        validate_json(root, current)
        required_roots(root, args.profile, changed)
        syntax_contracts(root, current)
    except (OSError, ValueError, json.JSONDecodeError, subprocess.CalledProcessError) as error:
        print(f"differential error: {error}", file=sys.stderr)
        return 2
    print(f"differential={args.profile} paths={len(changes)} PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
