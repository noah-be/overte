#!/usr/bin/env python3
"""Validate local branch creation and push destinations using an installed policy."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import re
import subprocess
import sys


class GuardError(ValueError):
    """A hook input or installed policy cannot be checked safely."""


def is_zero(oid: str) -> bool:
    return re.fullmatch(r"(?:0{40}|0{64})", oid) is not None


def check_oids(*oids: str) -> None:
    if len({len(oid) for oid in oids}) != 1 or any(
        re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", oid) is None for oid in oids
    ):
        raise GuardError("malformed Git object IDs in hook input")


def ref_exists(ref: str) -> bool:
    result = subprocess.run(
        ["git", "show-ref", "--verify", "--quiet", ref],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    if result.returncode not in (0, 1):
        raise GuardError("cannot determine whether the branch already exists")
    if result.returncode == 0:
        return True
    symbolic = subprocess.run(
        ["git", "symbolic-ref", "--quiet", ref],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    if symbolic.returncode not in (0, 1):
        raise GuardError("cannot determine whether a symbolic branch already exists")
    return symbolic.returncode == 0


def check_ref_values(*values: str) -> None:
    oids = []
    for value in values:
        if value.startswith("ref:"):
            result = subprocess.run(["git", "check-ref-format", value[4:]],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if result.returncode:
                raise GuardError("malformed symbolic ref in hook input")
        else:
            oids.append(value)
    if oids:
        check_oids(*oids)


def branch_names(hook: str, args: list[str], lines) -> list[str]:
    if hook == "reference-transaction":
        if len(args) != 1:
            raise GuardError("missing reference transaction state")
        if args[0] != "prepared":
            return []
        names = []
        for line in lines:
            parts = line.split()
            if len(parts) != 3:
                raise GuardError("malformed reference transaction input")
            old, new, ref = parts
            if not ref.startswith("refs/heads/"):
                continue
            check_ref_values(old, new)
            # Zero may also mean an unconditional update of an existing ref.
            if is_zero(old) and not is_zero(new) and not ref_exists(ref):
                names.append(ref.removeprefix("refs/heads/"))
        return names
    if hook == "pre-push":
        if len(args) != 2:
            raise GuardError("missing pre-push remote arguments")
        names = []
        for line in lines:
            parts = line.split()
            if len(parts) != 4:
                raise GuardError("malformed pre-push input")
            _, local_oid, destination, remote_oid = parts
            if not destination.startswith("refs/heads/"):
                continue
            check_oids(local_oid, remote_oid)
            if not is_zero(local_oid):
                names.append(destination.removeprefix("refs/heads/"))
        return names
    raise GuardError("unknown hook")


def validate_names(names: list[str]) -> None:
    if not names:
        return
    # The hook pins this immutable version, including its matching checker and policy.
    directory = Path(__file__).resolve().parent
    spec = importlib.util.spec_from_file_location("installed_branch_policy", directory / "check.py")
    if spec is None or spec.loader is None:
        raise GuardError("installed branch checker is unavailable")
    checker = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = checker
    spec.loader.exec_module(checker)
    policy = directory / "branch-policy.json"
    branches = checker.load_policy(policy)
    targets = checker.load_dependabot_targets(policy)
    for name in names:
        checker.validate_branch_name(branches, name, targets)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    try:
        if not args:
            raise GuardError("hook name is required")
        validate_names(branch_names(args[0], args[1:], sys.stdin))
    except (GuardError, ValueError, OSError, ImportError, AttributeError) as error:
        print(f"Branch name guard: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
