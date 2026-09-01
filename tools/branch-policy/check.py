#!/usr/bin/env python3
"""Validate pull-request direction against Overte's permanent branch hierarchy."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import argparse
import json
import os
import re
import subprocess
import sys
from urllib.parse import quote


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_POLICY = ROOT / ".github/branch-policy.json"
CHANGE_PREFIXES = (
    "feature", "fix", "docs", "refactor", "test", "tests", "ci", "sync"
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


@dataclass(frozen=True)
class ReconciliationAttestation:
    base_branch: str
    head_branch: str
    repository_id: int
    base_sha: str
    parent_sha: str
    head_sha: str
    privileged_entries: int


class GitHubBranchApi:
    """Read and compare GitHub objects without trusting pull-request code."""

    @staticmethod
    def _request(endpoint: str, label: str) -> dict:
        try:
            result = subprocess.run(
                ["gh", "api", endpoint],
                check=True,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except (OSError, subprocess.CalledProcessError, UnicodeDecodeError) as error:
            raise PolicyError(f"GitHub API failed while reading {label}") from error
        try:
            document = json.loads(result.stdout)
        except json.JSONDecodeError as error:
            raise PolicyError(f"GitHub API returned invalid JSON for {label}") from error
        if not isinstance(document, dict):
            raise PolicyError(f"GitHub API returned an invalid object for {label}")
        return document

    def branch_sha(self, repository: str, branch: str) -> str:
        endpoint = f"repos/{repository}/git/ref/heads/{quote(branch, safe='')}"
        document = self._request(endpoint, f"permanent branch {branch!r}")
        try:
            sha = document["object"]["sha"]
        except (KeyError, TypeError) as error:
            raise PolicyError(
                f"GitHub API omitted the SHA for permanent branch {branch!r}"
            ) from error
        validate_sha(sha, f"current {branch} SHA")
        return sha

    def commit_parents(self, repository: str, commit: str) -> tuple[str, ...]:
        document = self._request(
            f"repos/{repository}/git/commits/{commit}", "reconciliation merge commit"
        )
        if document.get("sha") != commit or not isinstance(document.get("parents"), list):
            raise PolicyError("GitHub API returned invalid reconciliation commit metadata")
        try:
            parents = tuple(parent["sha"] for parent in document["parents"])
        except (KeyError, TypeError) as error:
            raise PolicyError("GitHub API returned invalid reconciliation parents") from error
        for parent in parents:
            validate_sha(parent, "reconciliation parent SHA")
        return parents

    def compare(self, repository: str, ancestor: str, head: str) -> dict:
        return self._request(
            f"repos/{repository}/compare/{ancestor}...{head}",
            "reconciliation ancestry comparison",
        )

    def tree_entries(self, repository: str, commit: str) -> tuple[tuple[str, str, str, str], ...]:
        document = self._request(
            f"repos/{repository}/git/trees/{commit}?recursive=1",
            "reconciliation tree",
        )
        if document.get("truncated") is not False or not isinstance(document.get("tree"), list):
            raise PolicyError("GitHub API returned an incomplete reconciliation tree")
        entries = []
        seen = set()
        for entry in document["tree"]:
            try:
                path = entry["path"]
                mode = entry["mode"]
                object_type = entry["type"]
                sha = entry["sha"]
            except (KeyError, TypeError) as error:
                raise PolicyError(
                    "GitHub API returned malformed reconciliation tree data"
                ) from error
            if not all(isinstance(value, str) for value in (path, mode, object_type, sha)):
                raise PolicyError("GitHub API returned malformed reconciliation tree data")
            if path in seen:
                raise PolicyError("GitHub API returned duplicate reconciliation tree paths")
            seen.add(path)
            if not re.fullmatch(r"[0-7]{6}", mode) or object_type not in ("blob", "tree", "commit"):
                raise PolicyError("GitHub API returned malformed reconciliation tree metadata")
            validate_sha(sha, "tree object SHA")
            if changes_privileged_policy((path,)):
                entries.append((path, mode, object_type, sha))
        return tuple(sorted(entries))


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


def validate_sha(value: str, label: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 40
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise PolicyError(f"{label} must be a lowercase 40-character hexadecimal commit ID")


def reconciliation_prefix(branch: Branch) -> str:
    return f"reconcile/{branch.scope}/"


def is_exact_reconciliation_name(branch: Branch, head: str) -> bool:
    prefix = reconciliation_prefix(branch)
    name = head.removeprefix(prefix)
    return head.startswith(prefix) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", name) is not None


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

    if head.startswith("reconcile/"):
        if target.parent is None:
            raise PolicyError("the hierarchy root has no direct parent to reconcile")
        if is_exact_reconciliation_name(target, head):
            return "reconciliation"
        raise PolicyError(
            f"reconciliation branch {head!r} must match "
            f"{reconciliation_prefix(target)}<name> exactly"
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


def require_ancestor_comparison(document: dict, ancestor: str) -> None:
    try:
        status = document["status"]
        behind_by = document["behind_by"]
        base_sha = document["base_commit"]["sha"]
        merge_base_sha = document["merge_base_commit"]["sha"]
    except (KeyError, TypeError) as error:
        raise PolicyError("GitHub API returned malformed reconciliation comparison data") from error
    validate_sha(base_sha, "comparison base SHA")
    validate_sha(merge_base_sha, "comparison merge-base SHA")
    if (
        status not in ("ahead", "identical")
        or not isinstance(behind_by, int)
        or isinstance(behind_by, bool)
        or behind_by != 0
        or base_sha != ancestor
        or merge_base_sha != ancestor
    ):
        raise PolicyError("current permanent-branch SHA is not an ancestor of reconciliation head")


def attest_reconciliation(
    branches: dict[str, Branch],
    *,
    base: str,
    head: str,
    repository: str,
    repository_id: int,
    base_repository_id: int,
    head_repository_id: int,
    head_sha: str,
    api,
) -> ReconciliationAttestation:
    """Attest a direct parent-to-child conflict-resolution merge fail-closed."""
    if classify_pull_request(branches, base, head) != "reconciliation":
        raise PolicyError("reconciliation attestation requires an exact reconciliation branch")
    target = branches[base]
    if target.parent is None:
        raise PolicyError(f"target branch {base!r} has no direct permanent parent")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise PolicyError("repository must be an owner/name pair")
    if repository_id <= 0 or base_repository_id <= 0 or head_repository_id <= 0:
        raise PolicyError("repository IDs must be positive integers")
    if not (
        repository_id == base_repository_id == head_repository_id
    ):
        raise PolicyError(
            "reconciliation head, base, and direct parent must use the event repository"
        )
    validate_sha(head_sha, "head SHA")

    # Both values come from the live GitHub API. The parent is selected only
    # from the trusted policy's direct relationship, never from PR content.
    base_sha = api.branch_sha(repository, base)
    parent_sha = api.branch_sha(repository, target.parent)
    validate_sha(base_sha, f"current {base} SHA")
    validate_sha(parent_sha, f"current {target.parent} SHA")

    parents = api.commit_parents(repository, head_sha)
    if parents != (base_sha, parent_sha):
        raise PolicyError(
            "reconciliation head must be the direct merge of the current base "
            "and current direct parent, in that order"
        )
    require_ancestor_comparison(api.compare(repository, base_sha, head_sha), base_sha)
    require_ancestor_comparison(api.compare(repository, parent_sha, head_sha), parent_sha)

    parent_entries = api.tree_entries(repository, parent_sha)
    head_entries = api.tree_entries(repository, head_sha)
    if head_entries != parent_entries:
        raise PolicyError(
            "reconciliation privileged tree does not exactly match the current direct parent"
        )
    if (
        api.branch_sha(repository, base) != base_sha
        or api.branch_sha(repository, target.parent) != parent_sha
    ):
        raise PolicyError("permanent branch moved during reconciliation attestation")
    return ReconciliationAttestation(
        base_branch=base,
        head_branch=head,
        repository_id=repository_id,
        base_sha=base_sha,
        parent_sha=parent_sha,
        head_sha=head_sha,
        privileged_entries=len(parent_entries),
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
    reconciliation_attestation: ReconciliationAttestation | None = None,
) -> str:
    """Validate PR identity in addition to its branch-name direction."""
    classification = classify_pull_request(branches, base, head)

    if repository_id <= 0 or base_repository_id <= 0 or head_repository_id <= 0:
        raise PolicyError("repository IDs must be positive integers")
    if base_repository_id != repository_id:
        raise PolicyError("pull request base repository does not match the event repository")
    validate_sha(head_sha, "head SHA")

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

    if classification == "reconciliation":
        if reconciliation_attestation is None:
            raise PolicyError("reconciliation requires trusted API attestation")
        if (
            reconciliation_attestation.base_branch != base
            or reconciliation_attestation.head_branch != head
            or reconciliation_attestation.repository_id != repository_id
            or reconciliation_attestation.head_sha != head_sha
        ):
            raise PolicyError("reconciliation attestation does not match the pull request")

    if changes_privileged_policy(changed_files):
        same_repository_main_pr = (
            base == "main" and head_repository_id == base_repository_id
        )
        # Downstream syncs reach this point only after the same-repository and
        # exact current-parent SHA checks above have passed.
        verified_downstream_transfer = classification in (
            "downstream-sync", "reconciliation"
        )
        if not (same_repository_main_pr or verified_downstream_transfer):
            raise PolicyError(
                "privileged policy and workflow changes require a same-repository "
                "pull request to main or a verified direct-parent downstream sync"
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
    check.add_argument("--repository")
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
            classification = classify_pull_request(branches, args.base, args.head)
            reconciliation_attestation = None
            if classification == "reconciliation":
                repository = args.repository or os.environ.get("GITHUB_REPOSITORY")
                if not repository:
                    raise PolicyError(
                        "reconciliation requires the event repository for live attestation"
                    )
                reconciliation_attestation = attest_reconciliation(
                    branches,
                    base=args.base,
                    head=args.head,
                    repository=repository,
                    repository_id=args.repository_id,
                    base_repository_id=args.base_repository_id,
                    head_repository_id=args.head_repository_id,
                    head_sha=args.head_sha,
                    api=GitHubBranchApi(),
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
                reconciliation_attestation=reconciliation_attestation,
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
