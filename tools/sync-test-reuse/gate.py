#!/usr/bin/env python3
"""Fail-closed live verifier for exact-parent qualification reuse."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from fnmatch import fnmatch
from pathlib import Path
from urllib.parse import quote
import argparse
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import time
import zipfile


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / ".github/sync-test-reuse.json"
SHA_RE = re.compile(r"[0-9a-f]{40}")


class GateError(ValueError):
    """The request cannot be authorized as a sync."""


class EvidenceError(ValueError):
    """Qualification evidence is absent or unusable, requiring full fallback."""


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def digest_entries(entries: list[dict[str, str]]) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(entries)).hexdigest()


def parse_time(value: object, label: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise EvidenceError(f"{label} is not a UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise EvidenceError(f"{label} is invalid") from error
    return parsed


def validate_sha(value: object, label: str, error_type=GateError) -> str:
    if not isinstance(value, str) or not SHA_RE.fullmatch(value):
        raise error_type(f"{label} must be a full lowercase SHA")
    return value


class GitHubApi:
    """Small gh-backed API adapter; errors never degrade into authorization."""

    def json(self, endpoint: str, *, method: str = "GET", fields: dict[str, str] | None = None) -> object:
        command = ["gh", "api"]
        if method != "GET":
            command += ["--method", method]
        command.append(endpoint)
        for key, value in (fields or {}).items():
            command += ["-f", f"{key}={value}"]
        try:
            result = subprocess.run(
                command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True,
            )
            return json.loads(result.stdout) if result.stdout.strip() else {}
        except (OSError, subprocess.CalledProcessError, json.JSONDecodeError) as error:
            raise GateError(f"GitHub API request failed: {endpoint}") from error

    def bytes(self, endpoint: str) -> bytes:
        try:
            return subprocess.run(
                ["gh", "api", endpoint], check=True, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            ).stdout
        except (OSError, subprocess.CalledProcessError) as error:
            raise EvidenceError("qualification artifact download failed") from error


@dataclass(frozen=True)
class SyncRequest:
    repository: str
    repository_id: int
    number: int
    base: str
    base_sha: str
    head: str
    head_sha: str
    head_repository_id: int
    merge_sha: str
    classification: str
    parent: str
    parent_sha: str
    profile: str
    changed_paths: tuple[str, ...]


def load_config(path: Path = DEFAULT_CONFIG) -> dict:
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("schema") != 1 or not isinstance(document.get("edges"), dict):
        raise GateError("unsupported sync-test-reuse configuration")
    return document


def api_list(api: GitHubApi, endpoint: str, key: str) -> list[dict]:
    value = api.json(endpoint)
    if not isinstance(value, dict) or not isinstance(value.get(key), list):
        raise GateError(f"GitHub API omitted {key}")
    return value[key]


def branch_sha(api: GitHubApi, repository: str, branch: str) -> str:
    value = api.json(f"repos/{repository}/git/ref/heads/{quote(branch, safe='')}")
    try:
        return validate_sha(value["object"]["sha"], f"current {branch} SHA")  # type: ignore[index]
    except (KeyError, TypeError) as error:
        raise GateError(f"GitHub API omitted current {branch} SHA") from error


def commit(api: GitHubApi, repository: str, sha: str) -> dict:
    value = api.json(f"repos/{repository}/git/commits/{sha}")
    if not isinstance(value, dict) or value.get("sha") != sha:
        raise GateError("GitHub API returned mismatched commit metadata")
    return value


def commit_parents(document: dict) -> tuple[str, ...]:
    try:
        parents = tuple(validate_sha(item["sha"], "commit parent SHA") for item in document["parents"])
    except (KeyError, TypeError) as error:
        raise GateError("GitHub API returned invalid commit parents") from error
    return parents


def commit_tree(document: dict) -> str:
    try:
        return validate_sha(document["tree"]["sha"], "commit tree SHA")
    except (KeyError, TypeError) as error:
        raise GateError("GitHub API returned invalid commit tree") from error


def paginate_pull_files(api: GitHubApi, repository: str, number: int) -> list[dict]:
    files: list[dict] = []
    for page in range(1, 31):
        value = api.json(f"repos/{repository}/pulls/{number}/files?per_page=100&page={page}")
        if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
            raise GateError("GitHub API returned invalid pull-request file data")
        files.extend(value)
        if len(value) < 100:
            return files
    raise GateError("pull request exceeds the bounded changed-file audit")


def compare_files(api: GitHubApi, repository: str, base: str, head: str) -> tuple[str, set[str]]:
    value = api.json(f"repos/{repository}/compare/{base}...{head}")
    if not isinstance(value, dict) or not isinstance(value.get("files"), list):
        raise GateError("GitHub API returned incomplete ancestry comparison")
    try:
        merge_base = validate_sha(value["merge_base_commit"]["sha"], "merge-base SHA")
        files = {item["filename"] for item in value["files"]}
    except (KeyError, TypeError) as error:
        raise GateError("GitHub API returned malformed ancestry comparison") from error
    if any(not isinstance(path, str) for path in files):
        raise GateError("GitHub API returned an invalid comparison path")
    if len(files) >= 300:
        raise GateError("ancestry comparison reached the GitHub changed-file cap")
    return merge_base, files


def classify_event(event: dict, config: dict, api: GitHubApi) -> SyncRequest | None:
    try:
        repository = event["repository"]["full_name"]
        repository_id = int(event["repository"]["id"])
        pr = event["pull_request"]
        number = int(pr["number"])
        base = pr["base"]["ref"]
        base_sha = validate_sha(pr["base"]["sha"], "event base SHA")
        head = pr["head"]["ref"]
        head_sha = validate_sha(pr["head"]["sha"], "event head SHA")
        head_repository_id = int(pr["head"]["repo"]["id"])
    except (KeyError, TypeError, ValueError) as error:
        raise GateError("invalid pull_request_target event identity") from error
    if repository != config["repository"] or repository_id != config["repository_id"]:
        raise GateError("event repository does not match the trusted configuration")
    edge = config["edges"].get(base)
    if edge is None:
        return None
    parent = edge["parent"]
    scope = edge["scope"]
    direct = head == parent
    reconciliation = head.startswith(f"reconcile/{scope}/") and head.count("/") == 2
    if not direct and not reconciliation:
        return None
    if head_repository_id != repository_id:
        raise GateError("sync head must originate in the event repository")
    current_base = branch_sha(api, repository, base)
    current_parent = branch_sha(api, repository, parent)
    if current_base != base_sha:
        raise GateError("target head drifted after the pull-request event")
    if direct and head_sha != current_parent:
        raise GateError("direct synchronization does not use the current parent head")
    head_commit = commit(api, repository, head_sha)
    if reconciliation and commit_parents(head_commit) != (current_base, current_parent):
        raise GateError("reconciliation head is not the exact current base/parent merge")
    current_pr: object = None
    for attempt in range(6):
        current_pr = api.json(f"repos/{repository}/pulls/{number}")
        if (
            isinstance(current_pr, dict)
            and current_pr.get("mergeable") is not None
            and isinstance(current_pr.get("merge_commit_sha"), str)
        ):
            break
        if attempt < 5:
            time.sleep(3)
    if not isinstance(current_pr, dict):
        raise GateError("GitHub API returned invalid pull request metadata")
    if current_pr.get("state") != "open" or current_pr.get("mergeable") is False:
        raise GateError("pull request is closed or has merge conflicts")
    merge_sha = validate_sha(current_pr.get("merge_commit_sha"), "pull-request merge SHA")
    merge_commit = commit(api, repository, merge_sha)
    if commit_parents(merge_commit) != (current_base, head_sha):
        raise GateError("pull-request merge parents do not match current target and head")
    merge_base, parent_paths = compare_files(api, repository, current_parent, current_base)
    _, parent_delta = compare_files(api, repository, merge_base, current_parent)
    changed_documents = paginate_pull_files(api, repository, number)
    try:
        changed = tuple(sorted({item["filename"] for item in changed_documents}))
    except (KeyError, TypeError) as error:
        raise GateError("pull request contains malformed changed paths") from error
    if parent_paths and not isinstance(parent_paths, set):
        raise GateError("invalid ancestry comparison")
    unexpected = sorted(set(changed) - parent_delta)
    if unexpected:
        raise GateError("sync changes paths absent from the exact parent delta: " + ", ".join(unexpected[:10]))
    if branch_sha(api, repository, base) != current_base or branch_sha(api, repository, parent) != current_parent:
        raise GateError("target or parent head moved during topology validation")
    doc_only = bool(changed) and all(path.endswith(".md") or path.startswith("docs/") for path in changed)
    return SyncRequest(
        repository=repository, repository_id=repository_id, number=number,
        base=base, base_sha=current_base, head=head, head_sha=head_sha,
        head_repository_id=head_repository_id, merge_sha=merge_sha,
        classification="direct" if direct else "reconciliation", parent=parent,
        parent_sha=current_parent, profile="documentation" if doc_only else edge["differential"],
        changed_paths=changed,
    )


def recursive_tree(api: GitHubApi, repository: str, commit_sha: str, error_type=EvidenceError) -> tuple[str, dict[str, dict[str, str]]]:
    try:
        commit_document = commit(api, repository, commit_sha)
        tree_sha = commit_tree(commit_document)
        value = api.json(f"repos/{repository}/git/trees/{tree_sha}?recursive=1")
        if not isinstance(value, dict) or value.get("truncated") is not False or not isinstance(value.get("tree"), list):
            raise error_type("GitHub API returned an incomplete recursive tree")
        entries: dict[str, dict[str, str]] = {}
        for item in value["tree"]:
            if item.get("type") != "blob":
                continue
            entry = {key: item[key] for key in ("path", "mode", "type", "sha")}
            if not all(isinstance(entry[key], str) for key in entry) or entry["path"] in entries:
                raise error_type("GitHub API returned malformed or duplicate tree entries")
            entries[entry["path"]] = entry
        return tree_sha, entries
    except GateError as error:
        raise error_type(str(error)) from error


def select_entries(tree: dict[str, dict[str, str]], patterns: list[str]) -> list[dict[str, str]]:
    return sorted(
        (entry for path, entry in tree.items() if any(fnmatch(path, pattern) for pattern in patterns)),
        key=lambda item: item["path"],
    )


def artifact_evidence(api: GitHubApi, config: dict, request: SyncRequest) -> tuple[dict, dict]:
    workflow = quote(config["qualification_workflow"], safe="")
    endpoint = (
        f"repos/{request.repository}/actions/workflows/{workflow}/runs"
        f"?branch={quote(request.parent, safe='')}&event=push&status=success&per_page=100"
    )
    try:
        runs = [
            run for run in api_list(api, endpoint, "workflow_runs")
            if run.get("head_sha") == request.parent_sha and run.get("conclusion") == "success"
        ]
    except GateError as error:
        raise EvidenceError("qualification run lookup failed") from error
    if len(runs) != 1:
        raise EvidenceError("expected exactly one successful qualification run for the parent commit")
    run = runs[0]
    if run.get("event") != "push" or run.get("path") != config["qualification_workflow"]:
        raise EvidenceError("qualification run has an untrusted event or workflow path")
    try:
        suite = api.json(run.get("check_suite_url", ""))
    except GateError as error:
        raise EvidenceError("qualification check suite lookup failed") from error
    try:
        if suite["app"]["id"] != config["trusted_actions_app_id"] or suite["conclusion"] != "success":
            raise EvidenceError("qualification check suite is not a successful GitHub Actions run")
    except (KeyError, TypeError) as error:
        raise EvidenceError("qualification check suite identity is incomplete") from error
    try:
        artifacts = api_list(api, f"repos/{request.repository}/actions/runs/{run['id']}/artifacts", "artifacts")
    except GateError as error:
        raise EvidenceError("qualification artifact lookup failed") from error
    expected_name = config["evidence_artifact_prefix"] + request.parent_sha
    artifacts = [item for item in artifacts if item.get("name") == expected_name and not item.get("expired")]
    if len(artifacts) != 1:
        raise EvidenceError("expected exactly one live qualification artifact")
    raw = api.bytes(f"repos/{request.repository}/actions/artifacts/{artifacts[0]['id']}/zip")
    if len(raw) > 5_000_000:
        raise EvidenceError("qualification artifact exceeds the size limit")
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            if archive.namelist() != ["qualification.json"]:
                raise EvidenceError("qualification artifact has unexpected members")
            evidence = json.loads(archive.read("qualification.json"))
    except (zipfile.BadZipFile, KeyError, json.JSONDecodeError) as error:
        raise EvidenceError("qualification artifact is malformed") from error
    if not isinstance(evidence, dict):
        raise EvidenceError("qualification artifact root is not an object")
    return run, evidence


def verify_evidence(api: GitHubApi, config: dict, request: SyncRequest, now: datetime | None = None) -> dict:
    run, evidence = artifact_evidence(api, config, request)
    expected = {
        "schema": 1,
        "repository": request.repository,
        "repository_id": request.repository_id,
        "parent_branch": request.parent,
        "parent_commit": request.parent_sha,
    }
    for key, value in expected.items():
        if evidence.get(key) != value:
            raise EvidenceError(f"qualification evidence has mismatched {key}")
    parent_tree_sha, parent_tree = recursive_tree(api, request.repository, request.parent_sha)
    if evidence.get("parent_tree") != parent_tree_sha:
        raise EvidenceError("qualification evidence has a mismatched parent tree")
    entries = select_entries(parent_tree, config["qualified_inputs"])
    if evidence.get("qualified_inputs") != entries or evidence.get("qualified_inputs_digest") != digest_entries(entries):
        raise EvidenceError("qualification input manifest does not match the exact parent tree")
    if not set(config["required_qualified_inputs"]).issubset(parent_tree):
        raise EvidenceError("exact parent tree is missing required qualification inputs")
    workflow_entry = parent_tree.get(config["qualification_workflow"])
    workflow = evidence.get("workflow")
    if not isinstance(workflow, dict) or workflow_entry is None:
        raise EvidenceError("qualification workflow binding is incomplete")
    workflow_expected = {
        "path": config["qualification_workflow"],
        "blob_sha": workflow_entry["sha"],
        "ref": f"refs/heads/{request.parent}",
        "run_id": run["id"],
        "run_attempt": run["run_attempt"],
        "event": "push",
        "trusted_app_id": config["trusted_actions_app_id"],
    }
    if workflow != workflow_expected:
        raise EvidenceError("qualification workflow/run binding is mismatched")
    results = evidence.get("results")
    if not isinstance(results, dict) or results.get("conclusion") != "success" or results.get("suites") != ["project-quick", "device-control-plane-full"]:
        raise EvidenceError("qualification suite result is incomplete")
    now = now or datetime.now(timezone.utc)
    qualified = parse_time(evidence.get("qualified_at"), "qualified_at")
    expires = parse_time(evidence.get("expires_at"), "expires_at")
    max_age = int(config["evidence_max_age_hours"]) * 3600
    if qualified > now or expires <= now or (now - qualified).total_seconds() > max_age:
        raise EvidenceError("qualification evidence is stale or outside its validity window")
    unsigned = dict(evidence)
    actual_digest = unsigned.pop("evidence_digest", None)
    expected_digest = "sha256:" + hashlib.sha256(canonical_json(unsigned)).hexdigest()
    if actual_digest != expected_digest:
        raise EvidenceError("qualification evidence digest is invalid")
    _, merge_tree = recursive_tree(api, request.repository, request.merge_sha)
    for entry in entries:
        if merge_tree.get(entry["path"]) != entry:
            raise EvidenceError("qualified input changed in the expected merge tree: " + entry["path"])
    if branch_sha(api, request.repository, request.base) != request.base_sha or branch_sha(api, request.repository, request.parent) != request.parent_sha:
        raise EvidenceError("target or parent head moved during evidence validation")
    return evidence


def write_outputs(path: Path | None, values: dict[str, object]) -> None:
    lines = [f"{key}={str(value).lower() if isinstance(value, bool) else value}" for key, value in values.items()]
    if path:
        with path.open("a", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
    for line in lines:
        print(line)


def inspect(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    event = json.loads(args.event.read_text(encoding="utf-8"))
    api = GitHubApi()
    request = classify_event(event, config, api)
    if request is None:
        write_outputs(args.output, {"classification": "ordinary", "mode": "ordinary"})
        return 0
    mode, reason, evidence_run = "reuse", "exact qualification accepted", ""
    try:
        evidence = verify_evidence(api, config, request)
        evidence_run = str(evidence["workflow"]["run_id"])
    except EvidenceError as error:
        mode, reason = "fallback", str(error).replace("\n", " ")
    values = {
        "classification": request.classification,
        "mode": mode,
        "profile": request.profile,
        "repository": request.repository,
        "pr": request.number,
        "base": request.base,
        "base_sha": request.base_sha,
        "head_sha": request.head_sha,
        "parent": request.parent,
        "parent_sha": request.parent_sha,
        "merge_sha": request.merge_sha,
        "evidence_run_id": evidence_run,
        "reason": reason,
    }
    write_outputs(args.output, values)
    return 0


def dispatch_and_wait(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    api = GitHubApi()
    correlation = f"gate-{args.gate_run_id}"
    fields = {
        "ref": "main",
        "inputs[correlation]": correlation,
        "inputs[mode]": args.mode,
        "inputs[profile]": args.profile,
        "inputs[pull_request]": str(args.pull_request),
        "inputs[expected_base_sha]": args.base_sha,
        "inputs[expected_head_sha]": args.head_sha,
        "inputs[expected_merge_sha]": args.merge_sha,
    }
    api.json(
        f"repos/{args.repository}/actions/workflows/{config['validation_workflow']}/dispatches",
        method="POST", fields=fields,
    )
    deadline = time.monotonic() + args.timeout
    selected: dict | None = None
    while time.monotonic() < deadline:
        runs = api_list(
            api,
            f"repos/{args.repository}/actions/workflows/{config['validation_workflow']}/runs?event=workflow_dispatch&per_page=30",
            "workflow_runs",
        )
        matches = [run for run in runs if run.get("display_title") == f"Sync validation {correlation}"]
        if len(matches) > 1:
            raise GateError("validation run correlation is ambiguous")
        if matches:
            selected = matches[0]
            if selected.get("status") == "completed":
                if selected.get("conclusion") != "success":
                    raise GateError(f"{args.mode} validation did not succeed")
                write_outputs(args.output, {"validation_run_id": selected["id"], "validation_url": selected["html_url"]})
                return 0
        time.sleep(10)
    raise GateError("validation run did not reach a terminal success before timeout")


def cancel_redundant(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    api = GitHubApi()
    wanted = set(config["redundant_pull_request_workflows"])
    cancelled: set[int] = set()
    deadline = time.monotonic() + args.window
    while time.monotonic() < deadline:
        runs = api_list(
            api,
            f"repos/{args.repository}/actions/runs?event=pull_request&head_sha={args.head_sha}&per_page=100",
            "workflow_runs",
        )
        for run in runs:
            path = str(run.get("path", "")).rsplit("/", 1)[-1]
            pull_numbers = {item.get("number") for item in run.get("pull_requests", [])}
            if path not in wanted or args.pull_request not in pull_numbers:
                continue
            if run.get("status") in ("queued", "in_progress", "waiting", "pending") and run["id"] not in cancelled:
                try:
                    api.json(f"repos/{args.repository}/actions/runs/{run['id']}/cancel", method="POST")
                    cancelled.add(run["id"])
                except GateError as error:
                    print(f"warning: redundant run {run['id']} could not be cancelled: {error}", file=sys.stderr)
        time.sleep(5)
    print(f"cancelled_redundant_runs={len(cancelled)}")
    return 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    sub = result.add_subparsers(dest="command", required=True)
    inspect_parser = sub.add_parser("inspect")
    inspect_parser.add_argument("--event", type=Path, required=True)
    inspect_parser.add_argument("--output", type=Path)
    inspect_parser.set_defaults(handler=inspect)
    dispatch = sub.add_parser("dispatch-and-wait")
    dispatch.add_argument("--repository", required=True)
    dispatch.add_argument("--pull-request", type=int, required=True)
    dispatch.add_argument("--mode", choices=("reuse", "fallback"), required=True)
    dispatch.add_argument("--profile", required=True)
    dispatch.add_argument("--base-sha", required=True)
    dispatch.add_argument("--head-sha", required=True)
    dispatch.add_argument("--merge-sha", required=True)
    dispatch.add_argument("--gate-run-id", type=int, required=True)
    dispatch.add_argument("--timeout", type=int, default=1800)
    dispatch.add_argument("--output", type=Path)
    dispatch.set_defaults(handler=dispatch_and_wait)
    cancel = sub.add_parser("cancel-redundant")
    cancel.add_argument("--repository", required=True)
    cancel.add_argument("--pull-request", type=int, required=True)
    cancel.add_argument("--head-sha", required=True)
    cancel.add_argument("--window", type=int, default=60)
    cancel.set_defaults(handler=cancel_redundant)
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        return args.handler(args)
    except (GateError, OSError, json.JSONDecodeError) as error:
        print(f"sync gate error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
