#!/usr/bin/env python3
"""Enforce parent-owned and target-owned paths on Apple child branches."""

from __future__ import annotations

import argparse
import json
from pathlib import Path, PurePosixPath
import subprocess
import sys
from typing import Any


POLICY_PATH = "tests/apple-branch-path-ownership.json"
TARGETS = ("apple-ios",)


def git(repository: Path, *arguments: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", "-C", str(repository), *arguments],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def _decode(result: subprocess.CompletedProcess[bytes]) -> str:
    return result.stdout.decode("utf-8", errors="replace")


def _valid_path(value: Any, *, directory: bool) -> bool:
    if (not isinstance(value, str) or not value or "\\" in value
            or any(ord(character) < 32 for character in value)):
        return False
    if value.startswith("/") or value.endswith("/") != directory:
        return False
    without_separator = value[:-1] if directory else value
    path = PurePosixPath(without_separator)
    normalized = path.as_posix() + ("/" if directory else "")
    return (normalized == value and bool(path.parts)
            and all(part not in ("", ".", "..") for part in path.parts))


def _string_list(value: Any, *, directory: bool, label: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a list")
    if not all(_valid_path(item, directory=directory) for item in value):
        kind = "directory prefixes" if directory else "repository-relative files"
        raise ValueError(f"{label} must contain normalized {kind}")
    if len(value) != len(set(value)):
        raise ValueError(f"{label} contains duplicates")
    return value


def load_policy(repository: Path, apple_main: str) -> dict[str, Any]:
    result = git(repository, "show", f"{apple_main}:{POLICY_PATH}")
    if result.returncode != 0:
        raise ValueError(f"cannot load {POLICY_PATH} from apple-main")
    try:
        policy = json.loads(_decode(result))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid apple-main ownership policy: {exc}") from exc
    if not isinstance(policy, dict) or set(policy) != {
        "schemaVersion", "parentOwnedPrefixes", "parentOwnedFiles", "targets"
    }:
        raise ValueError("ownership policy has unexpected top-level fields")
    if policy["schemaVersion"] != 1:
        raise ValueError("ownership policy schemaVersion must be 1")

    parent_prefixes = _string_list(
        policy["parentOwnedPrefixes"], directory=True,
        label="parentOwnedPrefixes",
    )
    parent_files = _string_list(
        policy["parentOwnedFiles"], directory=False,
        label="parentOwnedFiles",
    )
    if POLICY_PATH not in parent_files:
        raise ValueError("ownership policy must protect itself")
    targets = policy["targets"]
    if not isinstance(targets, dict) or set(targets) != set(TARGETS):
        raise ValueError("ownership policy must define exactly apple-ios")

    for target in TARGETS:
        rules = targets[target]
        if not isinstance(rules, dict) or set(rules) != {"ownedPrefixes", "ownedFiles"}:
            raise ValueError(f"{target} ownership rules have unexpected fields")
        owned_prefixes = _string_list(
            rules["ownedPrefixes"], directory=True,
            label=f"{target}.ownedPrefixes",
        )
        owned_files = _string_list(
            rules["ownedFiles"], directory=False,
            label=f"{target}.ownedFiles",
        )
        for path in [*owned_prefixes, *owned_files]:
            if not any(path.startswith(prefix) for prefix in parent_prefixes):
                raise ValueError(f"{target} path is outside parent-owned prefixes: {path}")
            if path in parent_prefixes:
                raise ValueError(f"{target} cannot own an entire parent prefix: {path}")
            if path in parent_files:
                raise ValueError(f"{target} cannot own protected parent file: {path}")
    return policy


def _changed_paths(
    repository: Path,
    apple_main: str,
    head: str,
    pathspecs: list[str],
) -> tuple[list[tuple[str, str]], str | None]:
    result = git(
        repository, "diff", "--name-status", "--no-renames", "-z",
        apple_main, head, "--", *pathspecs,
    )
    if result.returncode != 0:
        return [], "cannot compare apple-main-owned paths"
    fields = result.stdout.split(b"\0")
    if fields and fields[-1] == b"":
        fields.pop()
    if len(fields) % 2:
        return [], "unexpected git diff output while checking ownership"
    changes = []
    for index in range(0, len(fields), 2):
        status = fields[index].decode("ascii", errors="replace")
        try:
            path = fields[index + 1].decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            return [], "non-UTF-8 path in parent-owned diff"
        changes.append((status, path))
    return changes, None


def _target_owns(path: str, rules: dict[str, list[str]]) -> bool:
    return path in rules["ownedFiles"] or any(
        path.startswith(prefix) for prefix in rules["ownedPrefixes"]
    )


def _unsafe_tree_entry(repository: Path, head: str, path: str) -> bool:
    result = git(repository, "ls-tree", "-z", head, "--", path)
    if result.returncode != 0:
        return True
    if not result.stdout:
        return False
    metadata = result.stdout.split(b"\t", 1)[0].split()
    return len(metadata) < 2 or metadata[0] in (b"120000", b"160000")


def validate(repository: Path, apple_main: str, head: str, target: str) -> list[str]:
    errors: list[str] = []
    if target not in TARGETS:
        return [f"unsupported Apple target: {target}"]

    base = git(repository, "rev-parse", "--verify", f"{apple_main}^{{commit}}")
    if base.returncode != 0:
        return ["cannot resolve current apple-main commit"]
    ancestry = git(repository, "merge-base", "--is-ancestor", apple_main, head)
    if ancestry.returncode != 0:
        errors.append(f"{target} must contain the current apple-main history")

    try:
        policy = load_policy(repository, apple_main)
    except (UnicodeDecodeError, ValueError) as exc:
        errors.append(str(exc))
        return errors

    parent_prefixes = policy["parentOwnedPrefixes"]
    parent_files = policy["parentOwnedFiles"]
    changes, diff_error = _changed_paths(
        repository, apple_main, head, [*parent_prefixes, *parent_files]
    )
    if diff_error:
        errors.append(diff_error)
        return errors

    rules = policy["targets"][target]
    for status, path in changes:
        if path in parent_files or not _target_owns(path, rules):
            errors.append(f"apple-main-owned path differs on {target}: {path}")
            continue
        if not status.startswith("D") and _unsafe_tree_entry(repository, head, path):
            errors.append(f"target-owned path has unsafe Git object type: {path}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--apple-main", default="origin/apple-main")
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--target", required=True, choices=TARGETS)
    args = parser.parse_args()
    errors = validate(
        args.repository.resolve(), args.apple_main, args.head, args.target
    )
    if errors:
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
        return 1
    print(f"PASS: Apple path ownership is valid for {args.target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
