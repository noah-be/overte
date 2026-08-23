#!/usr/bin/env python3
"""Validate pull-request direction against Overte's permanent branch hierarchy."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import argparse
import json
import sys


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_POLICY = ROOT / ".github/branch-policy.json"
CHANGE_PREFIXES = (
    "feature", "fix", "docs", "refactor", "test", "tests", "ci", "sync", "reconcile"
)


class PolicyError(ValueError):
    """A policy document or pull request violates the branch contract."""


@dataclass(frozen=True)
class Branch:
    name: str
    parent: str | None
    scope: str
    children: tuple[str, ...]


def load_policy(path: Path) -> dict[str, Branch]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PolicyError(f"cannot read policy {path}: {error}") from error
    if document.get("schema") != 1 or not isinstance(document.get("branches"), dict):
        raise PolicyError("policy must use schema 1 and contain a branches object")

    branches: dict[str, Branch] = {}
    for name, raw in document["branches"].items():
        try:
            branches[name] = Branch(name, raw["parent"], raw["scope"], tuple(raw["children"]))
        except (KeyError, TypeError) as error:
            raise PolicyError(f"invalid definition for {name}") from error

    scopes = [branch.scope for branch in branches.values()]
    if len(scopes) != len(set(scopes)):
        raise PolicyError("every permanent branch must have a unique scope")
    roots = [branch.name for branch in branches.values() if branch.parent is None]
    if roots != ["main"]:
        raise PolicyError("main must be the only hierarchy root")
    for branch in branches.values():
        if branch.parent is not None:
            if branch.parent not in branches:
                raise PolicyError(f"{branch.name} references unknown parent {branch.parent}")
            if branch.name not in branches[branch.parent].children:
                raise PolicyError(f"{branch.parent} does not list child {branch.name}")
        for child in branch.children:
            if child not in branches or branches[child].parent != branch.name:
                raise PolicyError(f"invalid child relationship {branch.name} -> {child}")
    return branches


def expected_prefixes(branch: Branch) -> tuple[str, ...]:
    scoped = tuple(f"{kind}/{branch.scope}/" for kind in CHANGE_PREFIXES)
    return scoped + (f"promote/{branch.scope}/",)


def classify_pull_request(branches: dict[str, Branch], base: str, head: str) -> str:
    if base not in branches:
        raise PolicyError(f"target branch {base!r} is not governed by the branch policy")
    target = branches[base]

    # A parent is allowed to flow wholesale into its direct child.
    if target.parent == head:
        return "downstream-sync"

    # A permanent child must never be merged wholesale back into a parent or sibling.
    if head in branches:
        relationship = "child" if base in branches[head].children else "unrelated permanent branch"
        raise PolicyError(
            f"blocked {relationship} merge {head} -> {base}; "
            f"only direct parent-to-child synchronization is allowed"
        )

    prefixes = expected_prefixes(target)
    if head.startswith(prefixes):
        return "promotion" if head.startswith(f"promote/{target.scope}/") else "scoped-change"

    expected = ", ".join(f"{prefix}<name>" for prefix in prefixes)
    raise PolicyError(
        f"branch {head!r} cannot target {base!r}; expected a direct parent sync or one of: {expected}"
    )


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    subparsers = parser.add_subparsers(dest="command", required=True)
    check = subparsers.add_parser("check-pr", help="validate a pull-request branch pair")
    check.add_argument("--base", required=True)
    check.add_argument("--head", required=True)
    children = subparsers.add_parser("children", help="print direct children, one per line")
    children.add_argument("--parent", required=True)
    subparsers.add_parser("validate", help="validate the policy document")
    return parser.parse_args()


def main() -> int:
    args = parse_arguments()
    try:
        branches = load_policy(args.policy)
        if args.command == "check-pr":
            classification = classify_pull_request(branches, args.base, args.head)
            print(f"allowed: {classification}: {args.head} -> {args.base}")
        elif args.command == "children":
            if args.parent not in branches:
                raise PolicyError(f"unknown permanent branch {args.parent!r}")
            print("\n".join(branches[args.parent].children))
        else:
            print(f"valid: {len(branches)} permanent branches")
    except PolicyError as error:
        print(f"branch policy violation: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
