#!/usr/bin/env python3
"""Detect parent-to-child branch drift without creating or merging pull requests."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen
import argparse
import json
import os
import sys

from check import Branch, PolicyError, load_policy


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_POLICY = ROOT / ".github/branch-policy.json"


class ApiError(RuntimeError):
    """A GitHub API operation failed or returned an invalid response."""


class BranchApi(Protocol):
    def branch_sha(self, repository: str, branch: str) -> str: ...
    def compare(self, repository: str, child: str, parent_sha: str) -> dict[str, Any]: ...


class GitHubApi:
    def __init__(self, token: str):
        if not token:
            raise ApiError("GITHUB_TOKEN is required")
        self.token = token

    def _get(self, path: str) -> dict[str, Any]:
        request = Request(
            f"https://api.github.com{path}",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "overte-read-only-branch-drift",
            },
        )
        try:
            with urlopen(request, timeout=30) as response:
                document = json.load(response)
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as error:
            raise ApiError(f"GET {path} failed: {error}") from error
        if not isinstance(document, dict):
            raise ApiError(f"GET {path} returned a non-object response")
        return document

    def branch_sha(self, repository: str, branch: str) -> str:
        document = self._get(
            f"/repos/{repository}/git/ref/heads/{quote(branch, safe='')}"
        )
        try:
            sha = document["object"]["sha"]
        except (KeyError, TypeError) as error:
            raise ApiError(f"branch response for {branch!r} has no object SHA") from error
        if not isinstance(sha, str):
            raise ApiError(f"branch response for {branch!r} has an invalid object SHA")
        return sha

    def compare(self, repository: str, child: str, parent_sha: str) -> dict[str, Any]:
        return self._get(
            f"/repos/{repository}/compare/{quote(child, safe='')}...{parent_sha}"
        )


@dataclass(frozen=True)
class Drift:
    parent: str
    child: str
    parent_sha: str
    ahead_by: int
    status: str


def validate_sha(value: str, label: str) -> None:
    if len(value) != 40 or any(character not in "0123456789abcdef" for character in value):
        raise PolicyError(f"{label} must be a lowercase 40-character hexadecimal commit ID")


def scan_parent(
    branches: dict[str, Branch],
    api: BranchApi,
    repository: str,
    parent: str,
    expected_parent_sha: str | None = None,
) -> list[Drift]:
    if parent not in branches or not branches[parent].children:
        raise PolicyError(f"{parent!r} is not a parent branch in the policy")

    current_parent_sha = api.branch_sha(repository, parent)
    validate_sha(current_parent_sha, f"current SHA for {parent}")
    if expected_parent_sha is not None:
        validate_sha(expected_parent_sha, f"expected SHA for {parent}")
        if current_parent_sha != expected_parent_sha:
            raise PolicyError(
                f"stale parent SHA for {parent}: event has {expected_parent_sha}, "
                f"current ref is {current_parent_sha}"
            )

    drifts = []
    for child in branches[parent].children:
        comparison = api.compare(repository, child, current_parent_sha)
        ahead_by = comparison.get("ahead_by")
        status = comparison.get("status")
        if not isinstance(ahead_by, int) or ahead_by < 0 or not isinstance(status, str):
            raise ApiError(f"compare response for {parent} -> {child} is invalid")
        if ahead_by:
            drifts.append(Drift(parent, child, current_parent_sha, ahead_by, status))
    return drifts


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--parent", action="append")
    parser.add_argument("--expected-parent-sha")
    return parser.parse_args()


def main() -> int:
    args = parse_arguments()
    try:
        branches = load_policy(args.policy)
        parents = args.parent or [
            branch.name for branch in branches.values() if branch.children
        ]
        if args.expected_parent_sha and len(parents) != 1:
            raise PolicyError("an expected parent SHA requires exactly one --parent")
        api = GitHubApi(os.environ.get("GITHUB_TOKEN", ""))
        drifts = []
        for parent in parents:
            drifts.extend(
                scan_parent(
                    branches,
                    api,
                    args.repository,
                    parent,
                    args.expected_parent_sha,
                )
            )
    except (ApiError, PolicyError) as error:
        print(f"branch drift detection failed closed: {error}", file=sys.stderr)
        return 2

    if drifts:
        print("## Branch synchronization drift detected")
        for drift in drifts:
            print(
                f"- `{drift.parent}` -> `{drift.child}`: "
                f"{drift.ahead_by} parent commit(s) missing (`{drift.parent_sha}`)"
            )
        print("\nNo pull request was selected, created, or merged.")
        return 1

    print("## Branch synchronization drift\n\nNo parent-to-child drift detected.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
