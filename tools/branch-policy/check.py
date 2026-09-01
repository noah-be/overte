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
PRIVILEGED_PATHS = (
    ".github/branch-policy.json",
    ".github/workflows/branch-policy.yml",
    ".github/workflows/branch-sync.yml",
    "tools/branch-policy/",
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


def changes_privileged_policy(paths: tuple[str, ...]) -> bool:
    return any(
        path == prefix or (prefix.endswith("/") and path.startswith(prefix))
        for path in paths
        for prefix in PRIVILEGED_PATHS
    )


def evaluate_pull_request(
    branches: dict[str, Branch],
    *,
    base: str,
    head: str,
    repository_id: int,
    base_repository_id: int,
    head_repository_id: int,
    head_sha: str,
    expected_head_sha: str | None = None,
    changed_files: tuple[str, ...] = (),
) -> str:
    """Validate PR identity in addition to its branch-name direction."""
    classification = classify_pull_request(branches, base, head)

    if repository_id <= 0 or base_repository_id <= 0 or head_repository_id <= 0:
        raise PolicyError("repository IDs must be positive integers")
    if base_repository_id != repository_id:
        raise PolicyError("pull request base repository does not match the event repository")
    if len(head_sha) != 40 or any(character not in "0123456789abcdef" for character in head_sha):
        raise PolicyError("head SHA must be a lowercase 40-character hexadecimal commit ID")

    if classification == "downstream-sync":
        if head_repository_id != base_repository_id:
            raise PolicyError(
                "direct parent synchronization must originate in the base repository"
            )
        if expected_head_sha is None:
            raise PolicyError("direct parent synchronization requires the current parent SHA")
        if head_sha != expected_head_sha:
            raise PolicyError(
                f"stale parent SHA: pull request has {head_sha}, current parent is {expected_head_sha}"
            )

    if changes_privileged_policy(changed_files):
        if base != "main" or head_repository_id != base_repository_id:
            raise PolicyError(
                "privileged policy and workflow changes require a same-repository pull request to main"
            )

    return classification


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    subparsers = parser.add_subparsers(dest="command", required=True)
    check = subparsers.add_parser("check-pr", help="validate a pull-request branch pair")
    check.add_argument("--base", required=True)
    check.add_argument("--head", required=True)
    check.add_argument("--repository-id", required=True, type=int)
    check.add_argument("--base-repository-id", required=True, type=int)
    check.add_argument("--head-repository-id", required=True, type=int)
    check.add_argument("--head-sha", required=True)
    check.add_argument("--expected-head-sha")
    check.add_argument("--changed-files-stdin", action="store_true")
    children = subparsers.add_parser("children", help="print direct children, one per line")
    children.add_argument("--parent", required=True)
    permanent = subparsers.add_parser("is-permanent", help="check whether a branch is permanent")
    permanent.add_argument("--branch", required=True)
    subparsers.add_parser("parents", help="print branches with direct children, one per line")
    subparsers.add_parser("validate", help="validate the policy document")
    return parser.parse_args()


def main() -> int:
    args = parse_arguments()
    try:
        branches = load_policy(args.policy)
        if args.command == "check-pr":
            changed_files = ()
            if args.changed_files_stdin:
                changed_files = tuple(
                    line for line in (item.strip() for item in sys.stdin) if line
                )
            classification = evaluate_pull_request(
                branches,
                base=args.base,
                head=args.head,
                repository_id=args.repository_id,
                base_repository_id=args.base_repository_id,
                head_repository_id=args.head_repository_id,
                head_sha=args.head_sha,
                expected_head_sha=args.expected_head_sha,
                changed_files=changed_files,
            )
            print(f"allowed: {classification}: {args.head} -> {args.base}")
        elif args.command == "children":
            if args.parent not in branches:
                raise PolicyError(f"unknown permanent branch {args.parent!r}")
            print("\n".join(branches[args.parent].children))
        elif args.command == "parents":
            print("\n".join(
                branch.name for branch in branches.values() if branch.children
            ))
        elif args.command == "is-permanent":
            if args.branch not in branches:
                raise PolicyError(f"branch {args.branch!r} is not permanent")
            print(f"permanent: {args.branch}")
        else:
            print(f"valid: {len(branches)} permanent branches")
    except PolicyError as error:
        print(f"branch policy violation: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
