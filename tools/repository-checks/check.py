#!/usr/bin/env python3
"""Offline routing and fail-closed aggregation for required repository checks."""

from __future__ import annotations

import argparse
import fnmatch
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
MODES = {"full", "documentation", "delegated-sync"}


def configuration(root: Path = ROOT) -> tuple[dict, dict]:
    config = json.loads((root / ".github/repository-checks.json").read_text())
    branches = json.loads((root / ".github/branch-policy.json").read_text())["branches"]
    if (config.get("schema") != 1 or config.get("repository") != "noah-be/overte"
            or config.get("repository_id") != 1319052603
            or config.get("documentation_suffixes") != [".md"]
            or not config.get("workflow_security_paths")):
        raise ValueError("invalid repository-check configuration")
    expected = {"dependency-release-policy", "branch-policy", "sync-test-reuse", "repository-checks"}
    if set(config.get("required_contexts", [])) != expected:
        raise ValueError("aggregate and independent synchronization gates must remain required")
    return config, branches


def plan(event: dict, paths: list[str], config: dict, branches: dict,
         documentation_safe: bool = True) -> dict[str, str]:
    """Unknown paths receive full validation; only explicit Markdown is lighter."""
    if any(not isinstance(path, str) or not path or "\x00" in path
           or PurePosixPath(path).is_absolute() or ".." in PurePosixPath(path).parts
           for path in paths):
        raise ValueError("invalid changed path")
    mode = "full"
    if documentation_safe and paths and all(PurePosixPath(path).suffix in config["documentation_suffixes"] for path in paths):
        mode = "documentation"
    security = not paths or any(fnmatch.fnmatchcase(path, pattern)
                               for path in paths for pattern in config["workflow_security_paths"])
    pr = event.get("pull_request")
    if pr is not None:
        repository = event["repository"]
        base, head = pr["base"], pr["head"]
        if (repository["full_name"] != config["repository"]
                or repository["id"] != config["repository_id"]
                or base["repo"]["id"] != config["repository_id"]
                or base["repo"]["full_name"] != config["repository"]):
            raise ValueError("pull request repository identity mismatch")
        target = branches.get(base["ref"])
        same_repository = (head.get("repo") or {}).get("id") == config["repository_id"]
        same_repository &= (head.get("repo") or {}).get("full_name") == config["repository"]
        if target and target["parent"] and same_repository:
            direct = head["ref"] == target["parent"]
            reconcile = re.fullmatch(r"reconcile/" + re.escape(target["scope"])
                                     + r"/[a-z0-9]+(?:-[a-z0-9]+)*", head["ref"])
            if direct or reconcile:
                # Direction, exact ancestry, current refs and actual candidate tests
                # are enforced by the independently required trusted sync gate.
                mode = "delegated-sync"
    return {"mode": mode, "security": str(security).lower()}


def changed_paths(candidate: Path, event: dict, expected_sha: str) -> tuple[list[str], bool]:
    def git(*args: str) -> str:
        return subprocess.check_output(["git", *args], cwd=candidate, text=True,
                                       stderr=subprocess.PIPE, timeout=30)

    if not re.fullmatch(r"[0-9a-f]{40}", expected_sha):
        raise ValueError("expected candidate must be a complete commit SHA")
    if git("rev-parse", "HEAD").strip() != expected_sha:
        raise ValueError("checkout is not the event candidate")
    pr = event.get("pull_request")
    if pr is None:
        return [], False  # Manual validation always takes the conservative full route.
    base_sha, head_sha = pr["base"]["sha"], pr["head"]["sha"]
    if not all(re.fullmatch(r"[0-9a-f]{40}", sha) for sha in (base_sha, head_sha)):
        raise ValueError("invalid pull request commit identity")
    parents = git("show", "--no-patch", "--format=%P", expected_sha).split()
    if parents != [base_sha, head_sha]:
        raise ValueError("candidate does not merge the exact event base and head")
    fields = git("diff", "--raw", "--no-renames", "-z", base_sha, expected_sha, "--").rstrip("\0").split("\0")
    if fields == [""]:
        return [], False
    if len(fields) % 2:
        raise ValueError("incomplete candidate change inventory")
    paths, documentation_safe = [], True
    for index in range(0, len(fields), 2):
        metadata = fields[index].split()
        if len(metadata) != 5 or not metadata[0].startswith(":"):
            raise ValueError("invalid candidate change metadata")
        modes = (metadata[0][1:], metadata[1])
        documentation_safe &= all(mode in {"000000", "100644"} for mode in modes)
        paths.append(fields[index + 1])
    return paths, documentation_safe


def verify(needs: dict) -> dict:
    expected_jobs = {"route", "project", "documentation", "workflow-security"}
    if not isinstance(needs, dict) or set(needs) != expected_jobs:
        raise ValueError("incomplete aggregate dependencies")
    if needs["route"].get("result") != "success":
        raise ValueError("routing did not succeed")
    outputs = needs["route"].get("outputs", {})
    mode, security = outputs.get("mode"), outputs.get("security")
    if mode not in MODES or security not in {"true", "false"}:
        raise ValueError("missing or invalid trusted route")
    required = {"documentation": "success",
                "project": "success" if mode == "full" else "skipped",
                "workflow-security": "success" if security == "true" else "skipped"}
    for job, conclusion in required.items():
        if needs[job].get("result") != conclusion:
            raise ValueError(f"{job}: expected {conclusion}, got {needs[job].get('result', 'missing')}")
    return {"status": "PASS", "mode": mode,
            "delegated_requirement": "sync-test-reuse" if mode == "delegated-sync" else None}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    route = commands.add_parser("plan")
    route.add_argument("--event", type=Path, required=True)
    route.add_argument("--candidate", type=Path, required=True)
    route.add_argument("--sha", required=True)
    route.add_argument("--output", type=Path, required=True)
    aggregate = commands.add_parser("verify")
    aggregate.add_argument("--needs-json", required=True)
    args = parser.parse_args()
    try:
        config, branches = configuration()
        if args.command == "plan":
            event = json.loads(args.event.read_text())
            paths, documentation_safe = changed_paths(args.candidate, event, args.sha)
            result = plan(event, paths, config, branches, documentation_safe)
            with args.output.open("a") as output:
                output.write("".join(f"{key}={value}\n" for key, value in result.items()))
        else:
            result = verify(json.loads(args.needs_json))
        print(json.dumps(result, sort_keys=True))
        return 0
    except (ValueError, KeyError, TypeError, OSError, subprocess.SubprocessError) as error:
        print(f"Repository checks failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
