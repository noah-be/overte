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
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import time
import zipfile

# Native source admission includes every import lookup member. Do not create
# bytecode in that protected lookup before it is independently authenticated.
sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / ".github/sync-test-reuse.json"
SHA_RE = re.compile(r"[0-9a-f]{40}")
_policy_spec = importlib.util.spec_from_file_location("sync_branch_policy", ROOT / "tools/branch-policy/check.py")
assert _policy_spec and _policy_spec.loader
branch_policy = importlib.util.module_from_spec(_policy_spec)
sys.modules[_policy_spec.name] = branch_policy
_policy_spec.loader.exec_module(branch_policy)
_tool_spec = importlib.util.spec_from_file_location(
    "sync_tool_dependencies", ROOT / "tools/repository-checks/tool_dependencies.py")
tool_dependencies = importlib.util.module_from_spec(_tool_spec)
_tool_spec.loader.exec_module(tool_dependencies)
_package_spec = importlib.util.spec_from_file_location(
    "sync_package_checks", ROOT / "tools/repository-checks/package_checks.py")
package_checks = importlib.util.module_from_spec(_package_spec)
_package_spec.loader.exec_module(package_checks)
_input_spec = importlib.util.spec_from_file_location(
    "sync_suite_inputs", ROOT / "tools/test-evidence/inputs.py")
suite_inputs = importlib.util.module_from_spec(_input_spec)
_input_spec.loader.exec_module(suite_inputs)


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


def safe_api_error(error: Exception) -> str:
    """Classify a failed CLI request without emitting commands or response text."""
    if isinstance(error, subprocess.CalledProcessError):
        stderr = error.stderr or ""
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")
        statuses = re.findall(r"\(HTTP ([1-5][0-9]{2})\)", stderr)
        status = statuses[-1] if statuses else "unknown"
        return f"command exit={error.returncode} http={status}"
    if isinstance(error, json.JSONDecodeError):
        return "invalid-json"
    if isinstance(error, OSError):
        return f"os-error errno={error.errno if error.errno is not None else 'unknown'}"
    return "unknown-error"


class GitHubApi:
    """Small gh-backed API adapter; errors never degrade into authorization."""

    def json(self, endpoint: str, *, method: str = "GET", fields: dict[str, str] | None = None,
             dispatch_details: bool = False) -> object:
        command = ["gh", "api"]
        if method != "GET":
            command += ["--method", method]
        command.append(endpoint)
        if dispatch_details:
            if method != "POST" or endpoint != "repos/noah-l-frank/overte/actions/workflows/sync-validation.yml/dispatches":
                raise GateError("run details are only supported for the fixed validation dispatch")
            command += ["-H", "X-GitHub-Api-Version: 2022-11-28",
                        "-F", "return_run_details=true"]
        for key, value in (fields or {}).items():
            command += ["-f", f"{key}={value}"]
        try:
            result = subprocess.run(
                command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True,
            )
            return json.loads(result.stdout) if result.stdout.strip() else {}
        except (OSError, subprocess.CalledProcessError, json.JSONDecodeError) as error:
            raise GateError(f"GitHub API request failed: {endpoint} ({safe_api_error(error)})") from error

    def bytes(self, endpoint: str) -> bytes:
        try:
            return subprocess.run(
                ["gh", "api", endpoint], check=True, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            ).stdout
        except (OSError, subprocess.CalledProcessError) as error:
            raise EvidenceError(f"qualification artifact download failed ({safe_api_error(error)})") from error

    def native_producer_api(self, controller):
        """Use the existing fixed-fork, versioned, bounded GET transport."""
        return controller.A.GitHubReadOnly()


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
    parent_changed_paths: tuple[str, ...]
    repair_paths: tuple[str, ...] = ()
    event_base_sha: str | None = None


@dataclass(frozen=True)
class EffectivePRContext:
    base: str
    head: str
    candidate: str
    event_base: str

    def planning(self):
        return {key: getattr(self, key) for key in ('base', 'head', 'candidate', 'event_base')}


def _base_source():
    spec = importlib.util.spec_from_file_location('sync_effective_base_source', ROOT / 'tools/test-evidence/source_admission.py')
    if spec is None or spec.loader is None:
        raise GateError('trusted live-base source resolver unavailable')
    source = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(source)
    return source


def _base_reader(api, repository):
    if repository != 'noah-l-frank/overte':
        raise GateError('effective base source is outside the reviewed fork')
    class Reader:
        def get(self, endpoint):
            return api.json('repos/' + repository + ('/' + endpoint if endpoint else ''))
    return Reader()


def _native_effective_role(api, event, live_base):
    """Authenticate fixed gate/validator roles before stale-base resolution."""
    env = os.environ
    if any(env.get(key) != value for key, value in {
            'GITHUB_ACTIONS': 'true', 'GITHUB_REPOSITORY': 'noah-l-frank/overte',
            'GITHUB_REPOSITORY_ID': '1319052603', 'GITHUB_RUN_ATTEMPT': '1'}.items()):
        raise GateError('target snapshot drifted; stale-base resolution needs an actual native synchronization role')
    repo = 'noah-l-frank/overte'
    pr = event['pull_request']; target = pr['base']['ref']
    try:
        identifier = int(env.get('GITHUB_RUN_ID', ''))
    except ValueError as error:
        raise GateError('native synchronization run unavailable') from error
    if identifier <= 0:
        raise GateError('native synchronization run unavailable')
    manual = env.get('GITHUB_EVENT_NAME') == 'workflow_dispatch'
    if manual:
        path, workflow, job, ref = '.github/workflows/sync-validation.yml', 350930895, 'validate', 'refs/heads/main'
        default = api.json(f'repos/{repo}/branches/main')
        if default.get('name') != 'main' or default.get('protected') is not True:
            raise GateError('native validation default source unavailable')
        source_sha = validate_sha(default.get('commit', {}).get('sha'), 'native validation source')
    else:
        path, workflow, job, ref = '.github/workflows/sync-test-reuse.yml', 350930894, 'sync-test-reuse', 'refs/heads/' + target
        source_sha = live_base
        if env.get('GITHUB_EVENT_NAME') != 'pull_request_target':
            raise GateError('unknown native synchronization role')
        if env.get('GITHUB_BASE_REF') != target or env.get('GITHUB_HEAD_REF') != pr['head']['ref']:
            raise GateError('native synchronization PR branch refs differ')
    if (env.get('GITHUB_JOB') != job or env.get('GITHUB_REF') != ref
            or env.get('GITHUB_SHA') != source_sha or env.get('GITHUB_WORKFLOW_SHA') != source_sha
            or env.get('GITHUB_WORKFLOW_REF') != repo + '/' + path + '@' + ref):
        raise GateError('native synchronization source/ref differs')

    def native_run(run_id, expected_source, expected_path, expected_workflow, expected_event):
        run = api.json(f'repos/{repo}/actions/runs/{run_id}')
        attempt = api.json(f'repos/{repo}/actions/runs/{run_id}/attempts/1')
        fields = ('id', 'workflow_id', 'check_suite_id', 'event', 'path', 'head_sha', 'head_branch',
                  'run_attempt', 'run_started_at', 'status', 'conclusion')
        if (any(run.get(key) != attempt.get(key) for key in fields)
                or (run.get('id'), run.get('workflow_id'), run.get('event'), run.get('path'), run.get('head_sha'), run.get('run_attempt')) !=
                   (run_id, expected_workflow, expected_event, expected_path, expected_source, 1)
                or run.get('head_branch') != ('main' if expected_event == 'workflow_dispatch' else pr['head']['ref'])
                or not (run.get('status') in {'queued', 'in_progress', 'waiting', 'pending'} and run.get('conclusion') is None
                        or run.get('status') == 'completed' and run.get('conclusion') == 'success')
                or any(document.get(key, {}).get('id') != 1319052603 or document[key].get('full_name') != repo
                       for document in (run, attempt) for key in ('repository', 'head_repository'))):
            raise GateError('native synchronization run/attempt/source unavailable')
        registration = api.json(f'repos/{repo}/actions/workflows/{expected_workflow}')
        suite = api.json(f'repos/{repo}/check-suites/{run["check_suite_id"]}')
        if (registration.get('id') != expected_workflow or registration.get('path') != expected_path or registration.get('state') != 'active'
                or suite.get('id') != run['check_suite_id'] or suite.get('head_sha') != expected_source or suite.get('app', {}).get('id') != 15368
                or suite.get('repository', {}).get('id') != 1319052603):
            raise GateError('native synchronization registration/App unavailable')
        try:
            started = parse_time(run.get('run_started_at'), 'native synchronization start')
        except EvidenceError as error:
            raise GateError('native synchronization start unavailable') from error
        if started > datetime.now(timezone.utc):
            raise GateError('native synchronization starts in the future')
        return run, attempt

    run, attempt = native_run(identifier, source_sha if manual else pr['head']['sha'], path, workflow, env['GITHUB_EVENT_NAME'])
    if manual:
        manual_started = parse_time(run.get('run_started_at'), 'native validation start')
        match = re.fullmatch(r'Sync validation gate-([1-9][0-9]*)-attempt-1', run.get('display_title', ''))
        if match is None:
            raise GateError('native validation gate handoff unavailable')
        run, attempt = native_run(int(match[1]), pr['head']['sha'], '.github/workflows/sync-test-reuse.yml', 350930894, 'pull_request_target')
        if parse_time(run.get('run_started_at'), 'native gate start') > manual_started:
            raise GateError('native validation precedes its original gate')
    associations = []
    for document in (run, attempt):
        associated = [row for row in document.get('pull_requests', []) if row.get('number') == pr['number']]
        if len(associated) != 1 or associated[0].get('base', {}).get('ref') != target or any(
                associated[0].get('head', {}).get(key) != pr['head'][key] for key in ('ref', 'sha')):
            raise GateError('native synchronization PR association unavailable')
        associations.append(associated[0])
    source = _base_source()
    try:
        reader = _base_reader(api, repo)
        for association in associations:
            source.validate_base_snapshot(reader, association.get('base', {}).get('sha'), live_base)
        default = reader.get('branches/main')
        if default.get('name') != 'main' or default.get('protected') is not True:
            raise GateError('trusted synchronization controller source unavailable')
        default_sha = validate_sha(default.get('commit', {}).get('sha'), 'trusted default source')
        actual = subprocess.check_output(['git', '--no-replace-objects', 'rev-parse', 'HEAD'], cwd=ROOT,
                                         stderr=subprocess.PIPE, timeout=30).decode().strip()
        if actual != default_sha:
            raise GateError('synchronization controller checkout differs from current default')
        for revision, recipe in ((source_sha, path), (live_base, '.github/workflows/sync-test-reuse.yml')):
            inventory = source.api_tree(reader, revision)
            row = subprocess.check_output(['git', '--no-replace-objects', 'ls-tree', default_sha, '--', recipe],
                                          cwd=ROOT, stderr=subprocess.PIPE, timeout=30).split()
            if len(row) != 4 or row[:2] != [b'100644', b'blob'] or inventory.get(recipe) != {
                    'mode': '100644', 'type': 'blob', 'sha': row[2].decode()}:
                raise GateError('native synchronization workflow recipe differs from protected controller source')
    except (source.SourceUnavailable, KeyError, TypeError, ValueError, OSError, subprocess.SubprocessError) as error:
        raise GateError('native synchronization base snapshot unavailable') from error


def effective_pr_context(event, api):
    """Return internal scheduling context only after fresh native/API proof."""
    pr = event['pull_request']; repo = event['repository']['full_name']
    snapshot = validate_sha(pr['base']['sha'], 'event base snapshot')
    live = branch_sha(api, repo, pr['base']['ref'])
    current = api.json(f'repos/{repo}/pulls/{pr["number"]}')
    if not isinstance(current, dict):
        raise GateError('current synchronization PR observation unavailable')
    if live == snapshot and current.get('base', {}).get('sha') == live:
        return None
    _native_effective_role(api, event, live)
    merge = api.json(f'repos/{repo}/commits/refs/pull/{pr["number"]}/merge')
    if commit_parents(merge) != (live, pr['head']['sha']):
        raise GateError('current synchronization merge does not use live base/head')
    source = _base_source()
    try:
        resolved = source.resolve_pr_base(_base_reader(api, repo), current, merge, event_pr=pr)
    except (source.SourceUnavailable, KeyError, TypeError, ValueError, OSError) as error:
        raise GateError('live synchronization base cannot be independently resolved') from error
    if resolved['base'] != live:
        raise GateError('protected synchronization base moved')
    return EffectivePRContext(resolved['base'], resolved['head'], resolved['source'], snapshot)


def immutable_change_documents(api, repository, base, candidate):
    """Complete B-to-M membership/mode/byte delta, never capped PR files."""
    _, before = recursive_tree(api, repository, base, error_type=GateError)
    _, after = recursive_tree(api, repository, candidate, error_type=GateError)
    return [{'filename': path, 'status': 'added' if path not in before else 'removed' if path not in after else 'modified'}
            for path in sorted(before.keys() | after.keys()) if before.get(path) != after.get(path)]


def recheck_effective_request(api, request, *, event_pr=None):
    """Reconstruct current source after work without editing an event snapshot."""
    repo = request.repository
    if branch_sha(api, repo, request.base) != request.base_sha:
        raise GateError('protected synchronization base ref changed after execution')
    current = api.json(f'repos/{repo}/pulls/{request.number}')
    event = {'repository': {'full_name': repo, 'id': request.repository_id}, 'pull_request': current}
    _native_effective_role(api, event, request.base_sha)
    source = _base_source()
    try:
        merge = api.json(f'repos/{repo}/commits/refs/pull/{request.number}/merge')
        if commit_parents(merge) != (request.base_sha, request.head_sha):
            raise GateError('current synchronization merge parents changed after execution')
        reader = _base_reader(api, repo)
        resolved = source.resolve_pr_base(reader, current, merge, event_pr=event_pr)
        source.validate_base_snapshot(reader, request.event_base_sha, resolved['base'])
    except (source.SourceUnavailable, KeyError, TypeError, ValueError, OSError) as error:
        raise GateError('effective synchronization context changed after execution') from error
    if (resolved['base'], resolved['head'], resolved['target'], resolved['head_ref'], resolved['source']) != (
            request.base_sha, request.head_sha, request.base, request.head, request.merge_sha):
        raise GateError('effective synchronization context changed after execution')
    if branch_sha(api, repo, request.base) != request.base_sha:
        raise GateError('protected synchronization base ref changed during recheck')
    observation = current if event_pr is None else event_pr
    return EffectivePRContext(request.base_sha, request.head_sha, request.merge_sha, observation['base']['sha'])


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


def changed_paths(documents: list[dict]) -> set[str]:
    """Audit both sides of renames; path spelling never grants authorization."""
    paths = set()
    for item in documents:
        if not isinstance(item, dict) or "filename" not in item:
            raise GateError("changed-file metadata is malformed")
        if item.get("status") == "renamed" and "previous_filename" not in item:
            raise GateError("renamed file is missing its source path")
        for key in ("filename", "previous_filename"):
            if key not in item:
                continue
            path = item[key]
            if (not isinstance(path, str) or not path or "\\" in path or "\x00" in path
                    or path.startswith("/") or any(part in ("", ".", "..") for part in path.split("/"))):
                raise GateError("changed-file path is unsafe")
            paths.add(path)
    return paths


def allowed_repair_paths(config: dict, base: str) -> set[str]:
    """Exact, nonprivileged paths from the trusted default-branch configuration."""
    mapping = config.get("reconciliation_repair_paths", {})
    if not isinstance(mapping, dict) or set(mapping) - set(config["edges"]):
        raise GateError("invalid reconciliation repair targets")
    paths = mapping.get(base, [])
    if (not isinstance(paths, list) or any(not isinstance(path, str) for path in paths)
            or len(paths) != len(set(paths))):
        raise GateError("invalid reconciliation repair paths")
    changed_paths([{"filename": path} for path in paths])
    if (any(any(char in path for char in "*?[]") for path in paths)
            or branch_policy.changes_privileged_policy(tuple(paths))):
        raise GateError("repair paths must be exact and nonprivileged")
    return set(paths)


def attest_product_repair(api, repository, repository_id, pr, current_pr,
                          base, parent, head, base_sha, parent_sha, head_sha, merge_sha, *, pr_context=None):
    """Reuse the unchanged branch-policy attestation, including its drift checks."""
    class BranchApi(branch_policy.GitHubBranchApi):
        def _request(self, endpoint, label):
            value = api.json(endpoint)
            if not isinstance(value, dict):
                raise branch_policy.PolicyError(f"invalid API object for {label}")
            return value

    try:
        if pr_context is not None:
            if not isinstance(pr_context, EffectivePRContext) or pr_context.planning() != {
                    'base': base_sha, 'head': head_sha, 'candidate': merge_sha,
                    'event_base': pr['base']['sha']}:
                raise GateError('repair effective base context differs from the current candidate')
            source = _base_source()
            try:
                for document in (pr, current_pr):
                    source.validate_base_snapshot(_base_reader(api, repository), document['base']['sha'], base_sha)
            except (source.SourceUnavailable, KeyError, TypeError, ValueError, OSError) as error:
                raise GateError('repair base snapshot is not an ancestor of the current target') from error
        for document in (pr, current_pr):
            for side, ref, sha in (("base", base, base_sha), ("head", head, head_sha)):
                identity = document[side]
                if (identity["repo"]["id"] != repository_id
                        or identity["repo"]["full_name"] != repository
                        or identity["ref"] != ref
                        or ((side == 'head' or pr_context is None) and identity["sha"] != sha)):
                    raise GateError("repair pull-request identity does not match the current event")
        adapter = BranchApi()
        branches = branch_policy.load_policy(branch_policy.DEFAULT_POLICY)
        if branches[base].parent != parent:
            raise GateError("repair parent does not match the trusted branch policy")
        attestation = branch_policy.attest_reconciliation(
            branches, base=base, head=head,
            repository=repository, repository_id=repository_id,
            base_repository_id=pr["base"]["repo"]["id"], head_repository_id=pr["head"]["repo"]["id"],
            head_sha=head_sha, api=adapter,
        )
        if attestation.base_sha != base_sha or attestation.parent_sha != parent_sha:
            raise GateError("repair attestation does not match the current sync parents")
        if adapter.tree_entries(repository, merge_sha) != adapter.tree_entries(repository, parent_sha):
            raise GateError("repair candidate privileged tree does not match the current direct parent")
    except (KeyError, TypeError, branch_policy.PolicyError) as error:
        raise GateError(f"product repair attestation failed: {error}") from error


def compare_files(api: GitHubApi, repository: str, base: str, head: str) -> tuple[str, set[str]]:
    value = api.json(f"repos/{repository}/compare/{base}...{head}")
    if not isinstance(value, dict) or not isinstance(value.get("files"), list):
        raise GateError("GitHub API returned incomplete ancestry comparison")
    try:
        merge_base = validate_sha(value["merge_base_commit"]["sha"], "merge-base SHA")
        files = changed_paths(value["files"])
    except (KeyError, TypeError) as error:
        raise GateError("GitHub API returned malformed ancestry comparison") from error
    if any(not isinstance(path, str) for path in files):
        raise GateError("GitHub API returned an invalid comparison path")
    if len(value["files"]) >= 300:
        if value.get("base_commit", {}).get("sha") != base:
            raise GateError("GitHub API returned a mismatched comparison base")
        # The compare endpoint caps file lists. Compare complete immutable
        # trees instead; never treat the truncated list as authorization.
        before = comparison_entries(api, repository, merge_base)
        after = comparison_entries(api, repository, head)
        files = {path for path in before.keys() | after.keys()
                 if before.get(path) != after.get(path)}
    return merge_base, files


def comparison_entries(api: GitHubApi, repository: str, sha: str) -> dict:
    tree_sha = commit_tree(commit(api, repository, sha))
    value = api.json(f"repos/{repository}/git/trees/{tree_sha}?recursive=1")
    if (not isinstance(value, dict) or value.get("sha") != tree_sha
            or value.get("truncated") is not False or not isinstance(value.get("tree"), list)):
        raise GateError("GitHub API returned an incomplete comparison tree")
    entries = {}
    for item in value["tree"]:
        if not isinstance(item, dict):
            raise GateError("GitHub API returned a malformed comparison entry")
        if item.get("type") == "tree":
            continue
        path = item.get("path")
        if (not isinstance(path, str) or not path or path.startswith("/")
                or ".." in path.split("/") or path in entries
                or item.get("type") not in ("blob", "commit")
                or item.get("mode") not in ("100644", "100755", "120000", "160000")):
            raise GateError("GitHub API returned an invalid comparison entry")
        entries[path] = {key: item[key] for key in ("mode", "type", "sha")}
        validate_sha(item.get("sha"), "comparison blob SHA")
    return entries


def authorize_retired_paths(api, repository, config, unexpected, changed_documents,
                            base_sha, parent_sha, merge_sha):
    """Allow only a named, exact legacy blob to disappear under parent policy."""
    retired = config.get("retired_parent_paths", {})
    changes = {item["filename"]: item for item in changed_documents}
    if any(path not in retired or path not in changes or changes[path].get("status") != "removed" for path in unexpected):
        raise GateError("sync changes paths absent from the exact parent delta: " + ", ".join(unexpected[:10]))
    base = comparison_entries(api, repository, base_sha)
    parent = comparison_entries(api, repository, parent_sha)
    merged = comparison_entries(api, repository, merge_sha)
    for path in unexpected:
        expected = {"mode": "100644", "type": "blob", "sha": retired[path]}
        validate_sha(retired[path], "retired parent-owned blob SHA")
        if base.get(path) != expected or path in parent or path in merged:
            raise GateError("retired parent-owned path does not match its exact deletion contract: " + path)


def compare_merge_base(api: GitHubApi, repository: str, base: str, head: str) -> str:
    """Read the exact merge base without trusting the capped comparison file list."""
    value = api.json(f"repos/{repository}/compare/{base}...{head}")
    if not isinstance(value, dict):
        raise GateError("GitHub API returned invalid ancestry comparison")
    try:
        compared_base = validate_sha(value["base_commit"]["sha"], "comparison base SHA")
        merge_base = validate_sha(value["merge_base_commit"]["sha"], "merge-base SHA")
    except (KeyError, TypeError) as error:
        raise GateError("GitHub API returned malformed ancestry comparison") from error
    if compared_base != base:
        raise GateError("GitHub API returned a mismatched comparison base")
    return merge_base


def classify_event(event: dict, config: dict, api: GitHubApi, *, pr_context=None) -> SyncRequest | None:
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
        if pr_context is None:
            pr_context = effective_pr_context(event, api)
        if not isinstance(pr_context, EffectivePRContext) or (pr_context.base, pr_context.head, pr_context.event_base) != (current_base, head_sha, base_sha):
            raise GateError("target head drifted after the pull-request event")
    elif pr_context is not None and (not isinstance(pr_context, EffectivePRContext)
            or (pr_context.base, pr_context.head, pr_context.event_base) != (current_base, head_sha, base_sha)):
        raise GateError('independently resolved synchronization context differs from the event')
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
            and (isinstance(current_pr.get("merge_commit_sha"), str)
                 or isinstance(pr_context, EffectivePRContext))
        ):
            break
        if attempt < 5:
            time.sleep(3)
    if not isinstance(current_pr, dict):
        raise GateError("GitHub API returned invalid pull request metadata")
    if current_pr.get("state") != "open" or current_pr.get("mergeable") is False:
        raise GateError("pull request is closed or has merge conflicts")
    merge_sha = (pr_context.candidate if isinstance(pr_context, EffectivePRContext)
                 else validate_sha(current_pr.get("merge_commit_sha"), "pull-request merge SHA"))
    merge_commit = commit(api, repository, merge_sha)
    if commit_parents(merge_commit) != (current_base, head_sha):
        raise GateError("pull-request merge parents do not match current target and head")
    merge_base = compare_merge_base(api, repository, current_parent, current_base)
    _, parent_delta = compare_files(api, repository, merge_base, current_parent)
    changed_documents = (immutable_change_documents(api, repository, current_base, merge_sha)
                         if isinstance(pr_context, EffectivePRContext) else paginate_pull_files(api, repository, number))
    changed = tuple(sorted(changed_paths(changed_documents)))
    allowed = allowed_repair_paths(config, base)
    repairs = tuple(sorted(set(changed) & allowed)) if reconciliation else ()
    if repairs:
        repair_context = {} if pr_context is None else {'pr_context': pr_context}
        attest_product_repair(api, repository, repository_id, pr, current_pr,
                              base, parent, head, current_base, current_parent, head_sha, merge_sha, **repair_context)
    unexpected = sorted(set(changed) - parent_delta - set(repairs))
    if unexpected:
        authorize_retired_paths(api, repository, config, unexpected, changed_documents,
                                current_base, current_parent, merge_sha)
        parent_delta.update(unexpected)
    if branch_sha(api, repository, base) != current_base or branch_sha(api, repository, parent) != current_parent:
        raise GateError("target or parent head moved during topology validation")
    doc_only = bool(changed) and all(
        item["filename"].endswith(".md")
        and item.get("previous_filename", item["filename"]).endswith(".md")
        for item in changed_documents
    )
    if doc_only and isinstance(pr_context, EffectivePRContext):
        _, before = recursive_tree(api, repository, current_base, error_type=GateError)
        _, after = recursive_tree(api, repository, merge_sha, error_type=GateError)
        doc_only = all(path not in inventory or (inventory[path]['mode'] == '100644' and inventory[path]['type'] == 'blob')
                       for inventory in (before, after) for path in changed)
    tool_only = False
    package_enabled = package_checks.activated(event)
    bounded_projects = (tool_dependencies.affected_projects(list(changed), include_s3=True)
                        if package_enabled else tool_dependencies.affected_projects(list(changed)))
    if not repairs and bounded_projects:
        # Both sides must be regular blobs. Include rename sources in `changed`
        # so an unrelated source/build path cannot disappear into this lane.
        tool_only = True
        for sha in (current_base, merge_sha):
            _, tree = recursive_tree(api, repository, sha, error_type=GateError)
            if package_checks.S3 in bounded_projects:
                try:
                    package_checks.validate_tree_wiring(tree)
                except ValueError as error:
                    raise GateError(str(error)) from error
            if any(path in tree and (tree[path]["mode"] != "100644" or tree[path]["type"] != "blob")
                   for path in changed):
                tool_only = False
        if branch_sha(api, repository, base) != current_base or branch_sha(api, repository, parent) != current_parent:
            raise GateError("target or parent head moved during tool manifest validation")
    profile = "documentation" if doc_only and not repairs else edge["differential"]
    if tool_only:
        profile = "tool-dependencies"
    if isinstance(pr_context, EffectivePRContext) and effective_pr_context(event, api) != pr_context:
        raise GateError('effective synchronization candidate changed during topology validation')
    return SyncRequest(
        repository=repository, repository_id=repository_id, number=number,
        base=base, base_sha=current_base, head=head, head_sha=head_sha,
        head_repository_id=head_repository_id, merge_sha=merge_sha,
        classification="direct" if direct else "reconciliation", parent=parent,
        parent_sha=current_parent, profile=profile,
        changed_paths=changed, parent_changed_paths=tuple(sorted(parent_delta)),
        repair_paths=repairs,
        event_base_sha=base_sha if isinstance(pr_context, EffectivePRContext) else None,
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
            if not isinstance(item, dict):
                raise error_type("GitHub API returned malformed tree data")
            if item.get("type") == "tree":
                continue
            if item.get("type") not in {"blob", "commit"}:
                raise error_type("GitHub API returned an unsupported tree object")
            try:
                entry = {key: item[key] for key in ("path", "mode", "type", "sha")}
            except KeyError as error:
                raise error_type("GitHub API omitted tree entry metadata") from error
            if not all(isinstance(entry[key], str) for key in entry) or entry["path"] in entries:
                raise error_type("GitHub API returned malformed or duplicate tree entries")
            changed_paths([{"filename": entry["path"]}])
            validate_sha(entry["sha"], "tree object SHA", error_type)
            if {"100644": "blob", "100755": "blob", "120000": "blob", "160000": "commit"}.get(entry["mode"]) != entry["type"]:
                raise error_type("GitHub API returned a mismatched tree mode and object type")
            entries[entry["path"]] = entry
        return tree_sha, entries
    except GateError as error:
        raise error_type(str(error)) from error


def validate_required_codeql_workflow(event: dict, api: GitHubApi, policy_root: Path = ROOT, *, pr_context=None) -> bool:
    """Protect result-verifier invocation before even an ordinary PR can pass.

    Activation and the finite approved workflow blobs belong to the trusted default
    checkout. A candidate config, job name or successful result cannot authorize
    replacing this workflow with an exit-only or fabricated security job.
    """
    policy = json.loads((policy_root / '.github/repository-checks.json').read_text(encoding='utf-8'))
    if not isinstance(policy, dict):
        raise GateError('invalid trusted CodeQL result activation policy')
    targets = policy.get('codeql_results_required_branches', [])
    permanent = {'main', 'apple-main', 'apple-ios', 'android-main', 'android-phone', 'android-vr', 'android-vr-pico'}
    if (policy.get('schema') != 1 or policy.get('repository') != 'noah-l-frank/overte'
            or policy.get('repository_id') != 1319052603 or not isinstance(targets, list)
            or any(not isinstance(target, str) or target not in permanent for target in targets)
            or len(targets) != len(set(targets))):
        raise GateError('invalid trusted CodeQL result activation policy')
    if not targets:
        return False
    try:
        pr = event['pull_request']
        base = pr['base']
        target = base['ref']
        if target not in permanent:
            raise GateError('invalid CodeQL result target')
        if target not in targets:
            return False
        head = pr['head']
        repository, repository_id = 'noah-l-frank/overte', 1319052603
        number = pr['number']
        if (type(number) is not int or number <= 0 or type(event.get('number')) is not int
                or event['number'] != number):
            raise GateError('invalid CodeQL result PR number')
        for identity in (event['repository'], base['repo'], head['repo']):
            if identity.get('full_name') != repository or identity.get('id') != repository_id:
                raise GateError('CodeQL result PR must belong to the reviewed fork')
        base_sha = validate_sha(base['sha'], 'CodeQL event base')
        head_sha = validate_sha(head['sha'], 'CodeQL event head')
        head_ref = head['ref']
        if (base_sha == '0' * 40 or head_sha == '0' * 40 or not isinstance(head_ref, str)
                or not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_./-]*', head_ref)
                or '..' in head_ref or '//' in head_ref or head_ref.endswith(('/', '.', '.lock'))
                or any(part.startswith('.') for part in head_ref.split('/'))):
            raise GateError('invalid CodeQL result head identity')
    except (KeyError, TypeError, AttributeError) as error:
        raise GateError('invalid CodeQL result event identity') from error
    spec = importlib.util.spec_from_file_location('sync_required_codeql_policy', policy_root / 'tools/repository-checks/codeql.py')
    if spec is None or spec.loader is None:
        raise GateError('trusted CodeQL workflow policy unavailable')
    trusted = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(trusted)
    generations = tuple(validate_sha(value, 'approved CodeQL result workflow')
                        for value in trusted.result_workflow_blobs())
    pairs = trusted.result_workflow_sources()
    if (type(pairs) is not tuple or len(pairs) != 5
            or any(type(row) is not tuple or len(row) != 2 for row in pairs)):
        raise GateError('approved CodeQL workflow/helper pairs unavailable')
    sources = {validate_sha(row[0], 'approved CodeQL result workflow'):
               None if row[1] is None else validate_sha(row[1], 'approved CodeQL metadata source')
               for row in pairs}
    approved = set(generations)
    metadata_workflow = validate_sha(trusted._METADATA_RESULTS_WORKFLOW, 'approved CodeQL metadata workflow')
    metadata_source = validate_sha(trusted._METADATA_SOURCE_WORKFLOW, 'approved CodeQL metadata source')
    if len(generations) != 5 or len(approved) != 5 or tuple(sources) != generations \
            or '0' * 40 in approved or any(sources[oid] is not None for oid in generations[:3]) \
            or pairs[3] != (metadata_workflow, metadata_source) \
            or pairs[4] != (trusted._SCHEDULING_RESULTS_WORKFLOW, trusted._SCHEDULING_SOURCE_WORKFLOW) \
            or any(value == '0' * 40 for value in sources.values()):
        raise GateError('approved CodeQL workflow identity is unavailable')
    refs = {f'repos/{repository}/git/ref/heads/{quote(ref, safe="")}': 'refs/heads/' + ref
            for ref in (target, head_ref)}

    class FixedForkReadOnly:
        def json(self, endpoint):
            if not isinstance(endpoint, str) or not endpoint.startswith('repos/' + repository + '/'):
                raise GateError('CodeQL invocation lookup escaped the reviewed fork')
            value = api.json(endpoint)
            if endpoint in refs and (not isinstance(value, dict) or value.get('ref') != refs[endpoint]
                                     or not isinstance(value.get('object'), dict) or value['object'].get('type') != 'commit'):
                raise GateError('CodeQL invocation branch reference identity mismatch')
            tree_prefix = 'repos/' + repository + '/git/trees/'
            if endpoint.startswith(tree_prefix):
                requested = endpoint[len(tree_prefix):].split('?', 1)[0]
                if not isinstance(value, dict) or value.get('sha') != requested:
                    raise GateError('CodeQL invocation tree identity mismatch')
            return value

    readonly = FixedForkReadOnly()
    snapshot = base_sha
    if pr_context is None and (branch_sha(readonly, repository, target) != snapshot
            or os.environ.get('GITHUB_ACTIONS') == 'true'):
        pr_context = effective_pr_context(event, api)
    if pr_context is not None:
        if not isinstance(pr_context, EffectivePRContext) or (pr_context.event_base, pr_context.head) != (snapshot, head_sha):
            raise GateError('invalid independently resolved CodeQL base context')
        base_sha = pr_context.base

    def fresh():
        if pr_context is not None and effective_pr_context(event, api) != pr_context:
            raise GateError('effective CodeQL base changed during verification')
        current = readonly.json(f'repos/{repository}/pulls/{number}')
        if (not isinstance(current, dict) or type(current.get('number')) is not int
                or current['number'] != number or current.get('state') != 'open'):
            raise GateError('CodeQL result PR is closed or unavailable')
        for side, ref, revision in (('base', target, base_sha), ('head', head_ref, head_sha)):
            value = current.get(side)
            if (not isinstance(value, dict) or value.get('ref') != ref
                    or ((side == 'head' or pr_context is None) and value.get('sha') != revision)
                    or not isinstance(value.get('repo'), dict) or value['repo'].get('full_name') != repository
                    or value['repo'].get('id') != repository_id
                    or branch_sha(readonly, repository, ref) != revision):
                raise GateError('CodeQL result PR or branch head changed')
        if current.get('mergeable') is False:
            raise GateError('CodeQL result PR has merge conflicts')
        if current.get('mergeable') is None or (pr_context is None and current.get('merge_commit_sha') is None):
            return None
        if current.get('mergeable') is not True:
            raise GateError('CodeQL result mergeability is unknown')
        candidate = (pr_context.candidate if pr_context is not None
                     else validate_sha(current.get('merge_commit_sha'), 'current CodeQL candidate'))
        if candidate == '0' * 40:
            raise GateError('invalid current CodeQL candidate')
        return candidate

    candidate = None
    for attempt in range(6):
        candidate = fresh()
        if candidate is not None:
            break
        if attempt < 5:
            time.sleep(3)
    if candidate is None:
        raise GateError('CodeQL candidate merge computation did not complete')
    merge = commit(readonly, repository, candidate)
    if commit_parents(merge) != (base_sha, head_sha):
        raise GateError('CodeQL candidate ordered parents differ from the current PR')
    tree_sha, tree = recursive_tree(readonly, repository, candidate, error_type=GateError)
    if tree_sha == '0' * 40 or tree_sha != commit_tree(merge):
        raise GateError('CodeQL candidate tree changed')
    actual = tree.get('.github/workflows/codeql.yml', {})
    if actual.get('mode') != '100644' or actual.get('type') != 'blob' or actual.get('sha') not in approved:
        raise GateError('candidate must retain the exact approved CodeQL security-result workflow')
    # The metadata successor invokes this relative reusable workflow. Its
    # exact caller blob cannot authorize candidate-controlled helper contents.
    if sources[actual['sha']] is not None and tree.get('.github/workflows/pr-metadata-context.yml') != {
            'path': '.github/workflows/pr-metadata-context.yml',
            'mode': '100644', 'type': 'blob', 'sha': sources[actual['sha']]}:
        raise GateError('candidate must retain the exact approved CodeQL metadata source workflow')
    _, base_tree = recursive_tree(readonly, repository, base_sha, error_type=GateError)
    previous = base_tree.get('.github/workflows/codeql.yml', {})
    if previous.get('mode') != '100644' or previous.get('type') != 'blob':
        raise GateError('CodeQL base workflow identity is unavailable or nonregular')
    if previous.get('sha') in approved and generations.index(actual['sha']) < generations.index(previous['sha']):
        raise GateError('deployed CodeQL result workflow cannot be reverted')
    if fresh() != candidate:
        raise GateError('CodeQL candidate changed during invocation verification')
    return True


def select_entries(tree: dict[str, dict[str, str]], patterns: list[str]) -> list[dict[str, str]]:
    return sorted(
        (entry for path, entry in tree.items() if any(fnmatch(path, pattern) for pattern in patterns)),
        key=lambda item: item["path"],
    )


def input_registry() -> dict:
    """Only default-branch policy may define the inputs of a reusable suite."""
    return suite_inputs.load_registry(ROOT / ".github/test-suites.json")


def input_tree(tree: dict[str, dict[str, str]]) -> dict[str, dict[str, str]]:
    return {path: {key: item[key] for key in ("mode", "type", "sha")}
            for path, item in tree.items()}


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


def _verify_legacy_evidence(api: GitHubApi, config: dict, request: SyncRequest, now: datetime | None = None) -> dict:
    run, evidence = artifact_evidence(api, config, request)
    expected = {
        "schema": 2,
        "repository": request.repository,
        "repository_id": request.repository_id,
        "parent_branch": request.parent,
        "parent_commit": request.parent_sha,
    }
    for key, value in expected.items():
        if evidence.get(key) != value:
            raise EvidenceError(f"qualification evidence has mismatched {key}")
    if evidence.get("reusable") is not True:
        raise EvidenceError("parent verification has no reusable runtime identity")
    if not isinstance(evidence.get("execution_receipt_digest"), str) or not re.fullmatch(
            r"sha256:[0-9a-f]{64}", evidence["execution_receipt_digest"]):
        raise EvidenceError("parent qualification omits its actual execution receipt identity")
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
    if not isinstance(results, dict) or results.get("conclusion") != "success" or not isinstance(results.get("suites"), dict):
        raise EvidenceError("qualification suite result is incomplete")
    try:
        registry = input_registry()
    except suite_inputs.InputError as error:
        raise EvidenceError("trusted suite input registry is unavailable") from error
    if set(results["suites"]) != set(registry["suites"]):
        raise EvidenceError("qualification does not contain the actual complete shared suite inventory")
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
    try:
        parent_inputs = input_tree(parent_tree)
        candidate_inputs = input_tree(merge_tree)
        environment = evidence.get("environment")
        for name, proof in results["suites"].items():
            if (not isinstance(proof, dict) or set(proof) != {"status", "fingerprint"}
                    or proof["status"] != "passed"
                    or proof["fingerprint"] != suite_inputs.suite_fingerprint(
                        registry, name, parent_inputs, environment)):
                raise EvidenceError("parent suite proof does not match its actual trusted input closure")
        # This is a source-only preview. The isolated validator compares its
        # actual installed runtime before consuming any reusable suite result.
        candidate_plan = suite_inputs.plan_reuse(
            registry, parent_inputs, candidate_inputs, results["suites"],
            environment, environment)
    except (suite_inputs.InputError, KeyError, TypeError) as error:
        raise EvidenceError("complete shared suite inputs or runtime identity are unavailable") from error
    if not candidate_plan["reused"]:
        raise EvidenceError("no shared suite has matching complete candidate inputs")
    if branch_sha(api, request.repository, request.base) != request.base_sha or branch_sha(api, request.repository, request.parent) != request.parent_sha:
        raise EvidenceError("target or parent head moved during evidence validation")
    return {**evidence, "candidate_plan": candidate_plan,
            "parent_inputs": parent_inputs, "candidate_inputs": candidate_inputs}


NATIVE_PARENT_KIND = 'original-native-parent-v1'


class NativeParentEvidence(dict):
    """Internal native API result; an artifact JSON field cannot create this."""


def _native_parent_controller():
    """Close the real protected import lookup before importing proof modules.

    ROOT is the trusted checkout, never the synchronization candidate. The
    immutable local source is subsequently bound to the live protected default
    by _native_sync_context; local Git metadata alone supplies no authority.
    """
    tree = suite_inputs.full_tree(ROOT, 'HEAD')
    name = 'tools/test-evidence/source_admission.py'
    path = ROOT / name
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        if current.is_symlink():
            raise EvidenceError('native parent source contains an alias')
    info = path.stat()
    if not path.is_file() or info.st_mode & 0o111 or info.st_size > 1_000_000:
        raise EvidenceError('native parent source helper is unavailable')
    raw = path.read_bytes()
    expected = {'mode': '100644', 'type': 'blob',
        'sha': hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()}
    if len(raw) > 1_000_000 or tree.get(name) != expected:
        raise EvidenceError('native parent source helper differs from immutable ROOT')
    guard = type(sys)('sync_native_parent_source_guard')
    guard.__file__ = str(path)
    exec(compile(raw, str(path), 'exec'), guard.__dict__)
    imports = {name: entry for name, entry in tree.items()
        if any(name == prefix or name.startswith(prefix+'/') for prefix in guard.IMPORT_ROOTS)}
    directories = sorted({str(parent) for name in imports for parent in Path(name).parents
        if any(str(parent) == prefix or str(parent).startswith(prefix+'/') for prefix in guard.IMPORT_ROOTS)})
    if set(imports) != set(guard.IMPORT_MEMBERS) or guard.actual_import_inventory(ROOT) != {
            'files': imports, 'directories': directories}:
        raise EvidenceError('native parent protected import lookup is not immutable')
    directory = str(ROOT / 'tools/test-evidence')
    sys.path.insert(0, directory)
    try:
        spec = importlib.util.spec_from_file_location('sync_native_parent_consumer', ROOT / 'tools/test-evidence/postmerge.py')
        controller = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(controller)
    finally:
        sys.path.remove(directory)
    for name in ('attested', 'ci_profile', 'execution', 'inputs', 'producer', 'producer_api',
                 'producer_workflow', 'runtime_ci', 'sandbox', 'source_admission'):
        module = sys.modules.get(name)
        if module is None or Path(module.__file__).resolve() != ROOT / ('tools/test-evidence/'+name+'.py'):
            raise EvidenceError('native parent proof module is outside actual protected ROOT')
    return controller


def _native_sync_context(controller, adapter, request):
    binding, references = adapter.current(request.number)
    expected = {'repository': request.repository, 'repository_id': request.repository_id,
        'pull_request': request.number, 'head_repository_id': request.head_repository_id,
        'base_ref': request.base, 'base_sha': request.base_sha, 'head_ref': request.head,
        'head_sha': request.head_sha, 'merge_sha': request.merge_sha,
        'merge_parents': [request.base_sha, request.head_sha]}
    controller.A.require(all(binding.get(key) == value for key, value in expected.items())
        and references['default_ref'] == 'main', 'native parent consumer source PR changed')
    branch = adapter._object('branches/'+quote(request.base, safe=''))
    controller.A.require(branch.get('name') == request.base and branch.get('protected') is True
        and branch.get('commit', {}).get('sha') == request.base_sha,
        'native parent consumer protected target changed')
    controller.default_authority(adapter, references)
    default_tree, local = controller.full_tree(adapter, references['default'])
    controller.A.require(controller.execution.checkout_identity(ROOT) == (references['default'], default_tree)
        and controller.inputs.full_tree(ROOT, references['default']) == local,
        'native parent actual ROOT differs from current default authority')
    return binding, references, local



def _empty_sync_invocation(controller, adapter, references, environment):
    """Authenticate the current dispatch, separately from its candidate PR M."""
    A = controller.A
    source = references['default']
    required = {'GITHUB_ACTIONS':'true','GITHUB_REPOSITORY':A.REPOSITORY,
        'GITHUB_REPOSITORY_ID':'1319052603','GITHUB_EVENT_NAME':'workflow_dispatch',
        'GITHUB_RUN_ATTEMPT':'1','GITHUB_JOB':'validate','GITHUB_REF':'refs/heads/main',
        'GITHUB_SHA':source,'GITHUB_WORKFLOW_SHA':source,
        'GITHUB_WORKFLOW_REF':A.REPOSITORY+'/.github/workflows/sync-validation.yml@refs/heads/main',
        'RUNNER_ENVIRONMENT':'github-hosted','ImageOS':'ubuntu24'}
    A.require(all(environment.get(key)==value for key,value in required.items()),
        'empty sync must use its actual protected native dispatch')
    run_id = A.positive(int(environment.get('GITHUB_RUN_ID','0')))
    registration = adapter._object('actions/workflows/sync-validation.yml')
    A.require(registration.get('id')==350930895 and registration.get('path')=='.github/workflows/sync-validation.yml'
        and registration.get('state')=='active' and registration.get('name')=='Sync validation',
        'empty sync workflow registration changed')
    latest = adapter._object('actions/runs/'+str(run_id))
    attempt = adapter._object(f'actions/runs/{run_id}/attempts/1')
    keys = ('id','workflow_id','check_suite_id','path','event','head_sha','head_branch',
        'run_attempt','status','conclusion','run_started_at')
    A.require(all(latest.get(key)==attempt.get(key) for key in keys)
        and attempt.get('id')==run_id and attempt.get('run_attempt')==1
        and attempt.get('workflow_id')==registration['id'] and attempt.get('path')==registration['path']
        and attempt.get('event')=='workflow_dispatch' and attempt.get('head_sha')==source
        and attempt.get('head_branch')=='main'
        and (attempt.get('status'),attempt.get('conclusion'))==('in_progress',None)
        and all(row.get(key,{}).get('id')==1319052603
            and row[key].get('full_name')==A.REPOSITORY
            for row in (latest,attempt) for key in ('repository','head_repository')),
        'empty sync is not its original current native attempt')
    suite = adapter._object('check-suites/'+str(A.positive(attempt.get('check_suite_id'))))
    A.require(suite.get('id')==attempt['check_suite_id'] and suite.get('head_sha')==source
        and suite.get('repository',{}).get('id')==1319052603 and suite.get('app',{}).get('id')==15368,
        'empty sync native check suite is foreign')
    jobs = adapter._pages(f'actions/runs/{run_id}/attempts/1/jobs','jobs')
    A.require(len(jobs)==1 and jobs[0].get('name')=='Validate exact synchronization',
        'empty sync native job inventory is incomplete or ambiguous')
    job = adapter._job(jobs[0],attempt,15368,final_name='Validate exact synchronization')
    A.require((job.status,job.conclusion)==('in_progress',None) and job.completed_at is None
        and controller.P._time(attempt.get('run_started_at'))<=controller.P._time(job.started_at)
        <=datetime.now(timezone.utc), 'empty sync native job is not currently executing')
    return {'registration':registration,'run':{key:attempt.get(key) for key in keys},'job':vars(job)}


def verified_empty_sync(api, config, request, candidate, *, environment=None):
    """Validation-only source proof; never original test/runtime qualification.

    The raw helper supplies immutable arithmetic only. Actual gate topology,
    native dispatch, protected default/controller and current PR bookends supply
    its authority. An unavailable proof leaves the existing execution route.
    """
    if request.changed_paths or request.repair_paths:
        return None
    try:
        controller = _native_parent_controller()
        A = controller.A
        A.require(config.get('repository')==A.REPOSITORY and config.get('repository_id')==1319052603
            and config.get('trusted_actions_app_id')==15368
            and config.get('validation_workflow')=='sync-validation.yml'
            and config['edges'][request.base]['parent']==request.parent,
            'empty sync requires the exact configured protected edge')
        adapter = A.Adapter(api.native_producer_api(controller))
        native = os.environ if environment is None else environment
        def observe():
            binding, refs, local = _native_sync_context(controller,adapter,request)
            invocation = _empty_sync_invocation(controller,adapter,refs,native)
            policy = controller.producer._host_policy()
            source = controller.producer.reuse_source_context(adapter,binding,refs,policy)
            tree_sha, current = controller.full_tree(adapter,request.merge_sha)
            before_sha, previous = controller.full_tree(adapter,request.base_sha)
            A.require(tree_sha==before_sha==binding['merge_tree'] and current==previous
                and controller.execution.checkout_identity(candidate)==(request.merge_sha,tree_sha)
                and suite_inputs.full_tree(candidate,request.merge_sha)==current,
                'empty sync complete immutable candidate inventory differs')
            package = policy.package_policy()
            A.require(package.validate_tree_wiring(current)==controller.ci_profile.RETAINED_SOURCE_GENERATION
                and current.get('.github/workflows/sync-validation.yml')==local.get(
                    'tools/repository-checks/workflows/sync-ci-selection.yml')
                and local.get('.github/workflows/sync-validation.yml')==local.get(
                    'tools/repository-checks/workflows/sync-ci-selection.yml'),
                'empty sync is not the complete reviewed future recipe')
            pr = adapter._object('pulls/'+str(request.number))
            labels = pr.get('labels')
            A.require(isinstance(labels,list) and all(type(label) is dict and type(label.get('name')) is str
                for label in labels) and not any(label['name']=='android-long-diagnostics' for label in labels),
                'explicit diagnostics cannot select an empty sync')
            checks = package.load('sync_empty_immutable_math','tools/repository-checks/check.py')
            proof = checks.immutable_empty_candidate(candidate,base_sha=request.base_sha,
                head_sha=request.head_sha,candidate_sha=request.merge_sha,
                merge_parents=(request.base_sha,request.head_sha))
            A.require(type(proof) is dict and proof.get('tree')==tree_sha,
                'empty sync raw immutable source proof is unavailable')
            return {'schema':1,'kind':'verified-empty-sync-v1','qualification':False,'reusable':False,
                'immutable':proof,'binding':binding,'references':refs,'source':source,'native':invocation}
        first = observe()
        A.require(observe()==first,'empty sync source or native context changed')
        return first
    except (EvidenceError,GateError,ValueError,OSError,KeyError,TypeError,AttributeError,ImportError,
            subprocess.SubprocessError):
        return None

def _native_parent_run(controller, adapter, request, now):
    endpoint = ('actions/workflows/350930890/runs?branch='+quote(request.parent, safe='')
        +'&event=push&head_sha='+request.parent_sha)
    rows = adapter._pages(endpoint, 'workflow_runs', search=True)
    controller.A.require(bool(rows) and all(row.get('head_sha') == request.parent_sha
        and row.get('head_branch') == request.parent and row.get('event') == 'push'
        and row.get('workflow_id') == 350930890
        and row.get('path') == '.github/workflows/parent-qualification.yml' for row in rows),
        'native parent run inventory is incomplete or foreign')
    times = [controller.P._time(row.get('run_started_at')) for row in rows]
    newest = max(times)
    controller.A.require(newest <= now and times.count(newest) == 1,
        'native parent newest run ordering is ambiguous')
    run = rows[times.index(newest)]
    controller.A.require(run.get('run_attempt') == 1 and run.get('status') == 'completed'
        and run.get('conclusion') == 'success', 'native parent newest push is not successful attempt one')
    return controller.A.positive(run.get('id')), rows


def native_parent_evidence(api, config, request, now=None):
    """Authenticate original native M, actual parent P and current child M.

    This is not a newly executed or renewed parent qualification artifact.
    The original receipt/E/lifetime stay attached to their real original M.
    """
    try:
        controller = _native_parent_controller()
        A, P = controller.A, controller.P
        A.require(controller._source_qualified() and request.repository == A.REPOSITORY
            and request.repository_id == 1319052603 and config['trusted_actions_app_id'] == 15368
            and config['qualification_workflow'] == '.github/workflows/parent-qualification.yml'
            and request.parent in {'main', 'android-main', 'android-vr', 'apple-main'}
            and config['edges'][request.base]['parent'] == request.parent and not request.repair_paths,
            'native parent source capability or exact direct edge is unavailable')
        clock = (lambda: now) if now is not None else lambda: datetime.now(timezone.utc)
        now = clock()
        P._now(now)
        adapter = A.Adapter(api.native_producer_api(controller))
        child_binding, child_refs, local = _native_sync_context(controller, adapter, request)
        push_id, push_inventory = _native_parent_run(controller, adapter, request, now)
        policy = controller.producer._host_policy()
        workflows, helpers = controller.producer.metadata_generations(policy, root=ROOT)
        metadata = None
        if workflows is not None:
            caller = adapter._object('actions/workflows/repository-checks.yml')
            A.require(caller.get('path') == '.github/workflows/repository-checks.yml',
                'retained original caller registration differs')
            metadata = A.MetadataPolicy(A.positive(caller.get('id')), '.github/workflows/repository-checks.yml',
                workflows, helpers)
        origin = adapter.integrated_origin(push_id, 15368, metadata, now=now)
        binding, references = origin.binding, origin.references
        A.require(binding['base_ref'] == request.parent and references['target'] == request.parent_sha
            and references['default'] == child_refs['default']
            and references['integration']['push_status'] == 'completed'
            and references['integration']['push_conclusion'] == 'success',
            'native parent/default completed context changed')
        tree_sha, parent = controller.full_tree(adapter, request.parent_sha)
        _, previous = controller.full_tree(adapter, binding['base_sha'])
        generation=policy.package_policy().validate_tree_wiring(parent)
        future=generation==controller.producer.PLATFORM_GENERATION
        parent_template=controller.producer.PLATFORM_PARENT_TEMPLATE if future else controller.TEMPLATE
        project_template=controller.producer.project_template(policy,parent)
        A.require(generation in controller.GENERATIONS
            and parent.get('.github/workflows/parent-qualification.yml') == local.get(parent_template),
            'native parent workflow is not a complete trusted consumer recipe')
        controller_check=controller.integrated_controller_for_reuse if future else controller.integrated_controller
        source = controller_check(policy, previous, parent, local, request.parent, ROOT)
        registry = controller.inputs.load_registry(ROOT / '.github/test-suites.json')
        A.require(all(suite['scope'] == 'content' for suite in registry['suites'].values())
            and all(tree.get('.github/test-suites.json') == local.get('.github/test-suites.json')
                    for tree in (previous, parent)), 'native parent command registry differs from protected source')
        context = previous if request.parent == 'main' else local
        read_blob = adapter.api.immutable_blob
        selector=controller.producer.selection_profile_for_reuse if future else controller.producer.selection_profile
        profile = selector(policy, registry, parent, previous, context,
            root=ROOT, target=request.parent, read_blob=read_blob)
        selected = profile['selection']
        affected = controller._affected_receipt_selection(profile, registry, request.parent)
        partition=controller.producer.platform_partition(policy,profile,registry,parent,previous,local,
            target=request.parent,root=ROOT,read_blob=read_blob)
        if partition is None:
            A.require(controller.source_admission.shared_platform_supported(selected, request.parent,
                parent.get(controller.source_admission.PROFILE)), 'native parent product ownership is unavailable')
        owner=controller.producer.common_owner(profile,partition)
        plan, api_policy = controller._policy(policy, registry, binding, source, adapter, ROOT, selected,
            common_owner=owner,template=project_template)
        snapshot = adapter.capture_integrated(push_id, plan, api_policy, now=now)
        A.require(snapshot.references == references, 'native parent integration changed before proof selection')
        if future:
            profile,context=controller.producer.reuse_source_profile(snapshot,adapter,api_policy,policy,registry,
                parent,previous,root=ROOT,target=request.parent,read_blob=read_blob,now=clock())
            selected=profile['selection'];affected=controller._affected_receipt_selection(profile,registry,request.parent)
            partition=controller.producer.platform_partition(policy,profile,registry,parent,previous,local,
                target=request.parent,root=ROOT,read_blob=read_blob)
            owner=controller.producer.common_owner(profile,partition)
            plan,api_policy=controller._policy(policy,registry,binding,source,adapter,ROOT,selected,
                common_owner=owner,template=project_template)
        original_tree, original = controller.full_tree(adapter, snapshot.binding['merge_sha'])
        A.require(original_tree == tree_sha == snapshot.binding['merge_tree'] and original == parent
            and selector(policy, registry, original, previous, context,
                root=ROOT, target=request.parent, read_blob=read_blob) == profile,
            'native original source differs from exact parent inputs')
        A.require(controller.producer.platform_partition(policy,profile,registry,original,previous,local,
            target=request.parent,root=ROOT,read_blob=read_blob)==partition,
            'native original and current parent platform ownership differs')
        authority = P.select_authority(snapshot.observations, snapshot.binding, plan, api_policy.producer,
            inventory_complete=snapshot.inventory_complete, now=now)
        A.require(authority['state'] == 'proof-required', 'native parent original producer is unresolved')
        observation = next(item for item in snapshot.observations if item.run.run_id == authority['run_id'])
        platform_observation=(controller.original_platform_owner(adapter,observation.run,partition,now=clock())
            if partition is not None else None)
        raw, facts = adapter._artifact(observation.run, 'aggregate',
            snapshot.artifact_inventories[authority['run_id']], now, snapshot.binding['head_sha'])
        aggregate = P.read_artifact(raw, 'aggregate', facts, observation.run, now=now)
        receipt = aggregate.get('results', {}).get('shared-host', {}).get('receipt')
        A.require(type(receipt) is dict and receipt.get('schema') == api_policy.producer.required_execution_schema,
            'native parent versioned original receipt unavailable')
        git_context = controller.producer.expected_git_context(adapter, snapshot.binding)
        controller.execution.validate_receipt(receipt, registry, original,
            require_all=profile['profile'] != controller.ci_profile.PROFILE and not affected,
            expected_git_context=git_context)
        A.require(receipt['requested_suites'] == selected['suites']
            and receipt['include_platform'] == owner['include_platform']
            and (partition is None or receipt['platform_results']=={}), 'native parent selected owner differs')
        environment = receipt['environment']
        retained=controller.producer.retained_receipt_source(receipt,snapshot.binding,adapter,registry,selected,
            authority['run_id'],root=ROOT)
        shared = P.SharedContext(registry, original, environment, snapshot.binding['merge_sha'], tree_sha, git_context,retained)
        original_source=None
        if receipt['schema']==4:
            verified,original_source=controller.producer.verify_original_source(adapter,push_id,plan,api_policy,
                shared,receipt,snapshot.binding,integrated=True,root=ROOT,clock=clock)
        if profile['profile'] == controller.ci_profile.PROFILE:
            ci_context = ({'base_tree': previous}
                if profile['binding'].get('generation_kind') == controller.ci_profile.SEVEN_CONTROLLER_KIND else {})
            validator=(controller.runtime_ci.validate_environment if original_source is None else
                lambda *args,**kwargs:controller.runtime_ci.validate_original_environment(original_source,*args,**kwargs))
            admission = validator(environment, aggregate.get('qualified_at'),
                aggregate.get('expires_at'), now, selected, original, context, registry,
                root=ROOT, target=request.parent, read_blob=read_blob, **ci_context)
        else:
            admission = controller.attested.validate_environment(environment, aggregate.get('qualified_at'),
                aggregate.get('expires_at'), now, root=ROOT, isolated=True)
        if original_source is None:
            verified=adapter.verify_integrated(push_id,plan,api_policy,{'shared-host':shared},clock=clock)
        else:
            A.require(A.Adapter.verify_integrated(adapter,push_id,plan,api_policy,{'shared-host':shared},clock=clock)==verified,
                'native parent original proof changed during runtime/source admission')
        if partition is not None:
            A.require(controller.original_platform_owner(adapter,observation.run,partition,now=clock())==platform_observation,
                'native original Android platform job changed during common proof verification')
        A.require(verified['integration'] == references['integration']
            and verified['receipt_sha256'] == hashlib.sha256(P.canonical(receipt)).hexdigest()
            and verified['aggregate_digest'] == aggregate['aggregate_digest']
            and 0 <= (clock() - P._time(verified['qualified_at'])).total_seconds()
                <= int(config['evidence_max_age_hours']) * 3600,
            'native parent whole proof or allowed lifetime changed')
        _, candidate = controller.full_tree(adapter, request.merge_sha)
        A.require(candidate.get(controller.source_admission.PROFILE)==controller.source_admission.ordinary(
            controller.source_admission.TARGET_PROFILES[request.base]),
            'current child platform declaration needs its actual known owner')
        A.require(all(entry['mode'] in {'100644', '100755'} and entry['type'] == 'blob'
            for tree in (parent, candidate) for entry in tree.values()), 'native parent reuse requires ordinary complete inputs')
        candidate_plan = controller.inputs.plan_reuse(registry, parent, candidate, receipt['results'], environment, environment)
        final = _native_sync_context(controller, adapter, request)
        A.require(final == (child_binding, child_refs, local)
            and _native_parent_run(controller, adapter, request, clock()) == (push_id, push_inventory)
            and adapter.integrated_origin(push_id, 15368, metadata, now=clock()) == origin
            and controller_check(policy, previous, parent, local, request.parent, ROOT) == source
            and controller.producer.retained_receipt_source(receipt,snapshot.binding,adapter,registry,selected,authority['run_id'],root=ROOT)==retained
            and controller.producer.platform_partition(policy,profile,registry,parent,previous,local,
                target=request.parent,root=ROOT,read_blob=read_blob)==partition
            and (partition is None or controller.original_platform_owner(adapter,observation.run,partition,now=clock())==platform_observation)
            and clock() < P._time(verified['expires_at']),
            'native parent/default/source context changed before completion')
        A.require(bool(candidate_plan['reused']), 'native parent has no matching child suite source')
        return NativeParentEvidence({'kind': NATIVE_PARENT_KIND, 'parent_branch': request.parent, 'parent_commit': request.parent_sha,
            'parent_tree': tree_sha, 'original_commit': snapshot.binding['merge_sha'], 'original_git_context': git_context,
            'qualified_at': verified['qualified_at'], 'expires_at': verified['expires_at'],
            'environment': environment, 'results': {'conclusion': 'success', 'suites': receipt['results']},
            'child_platform_profile':candidate[controller.source_admission.PROFILE], 'platform_reused':False,
            'original_platform_observation':platform_observation,
            'original_proof': verified, 'original_protected_source':retained, 'runtime_admission': admission, 'candidate_plan': candidate_plan,
            'parent_inputs': parent, 'candidate_inputs': candidate})
    except EvidenceError:
        raise
    except (OSError, ValueError, KeyError, TypeError, AttributeError, ImportError, subprocess.SubprocessError) as error:
        raise EvidenceError('original native parent proof unavailable; actual synchronization execution is required') from error


def verify_evidence(api: GitHubApi, config: dict, request: SyncRequest, now: datetime | None = None) -> dict:
    try:
        return _verify_legacy_evidence(api, config, request, now)
    except EvidenceError:
        # Preserve legacy2 routes exactly. The native path requires the fixed
        # bounded transport explicitly, never an arbitrary JSON/proof fallback.
        if not callable(getattr(api, 'native_producer_api', None)):
            raise
        return native_parent_evidence(api, config, request, now)


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
    context = (effective_pr_context(event, api) if os.environ.get('GITHUB_ACTIONS') == 'true'
               and os.environ.get('GITHUB_EVENT_NAME') == 'pull_request_target' else None)
    if context is None:
        validate_required_codeql_workflow(event, api)
        request = classify_event(event, config, api)
    else:
        validate_required_codeql_workflow(event, api, pr_context=context)
        request = classify_event(event, config, api, pr_context=context)
    if request is None:
        write_outputs(args.output, {"classification": "ordinary", "mode": "ordinary"})
        return 0
    mode, reason, evidence_run = "reuse", "exact qualification accepted", ""
    if request.repair_paths:
        mode, reason = "fallback", "attested product repair requires complete fallback"
    elif request.profile == "documentation":
        reason = "documentation-only delta; no executable inputs require qualification"
    elif request.profile == "tool-dependencies":
        reason = "bounded tool manifest delta; affected tool checks required"
    else:
        try:
            evidence = verify_evidence(api, config, request)
            plan = evidence["candidate_plan"]
            if isinstance(evidence, NativeParentEvidence):
                evidence_run = str(evidence['original_proof']['run_id'])
                reason = (f"original native parent proofs accepted; {len(plan['reused'])} source matches, "
                          f"{len(plan['required'])} suites require candidate execution; original proof rechecked in validation")
            else:
                evidence_run = str(evidence["workflow"]["run_id"])
                reason = (f"exact parent suite proofs accepted; {len(plan['reused'])} source matches, "
                          f"{len(plan['required'])} suites require candidate execution; runtime rechecked in validation")
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


def _dispatch_checkout_source() -> str:
    """Bind the actual default-branch checkout, not the parent run's PR head."""
    try:
        result = subprocess.run(
            ["git", "--no-optional-locks", "--no-replace-objects", "rev-parse", "--verify", "HEAD^{commit}"],
            cwd=ROOT, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise GateError("trusted dispatch checkout source is unavailable") from error
    return validate_sha(result.stdout.strip(), "trusted dispatch checkout source")


def _dispatch_source(api, config, repository, checkout_source):
    if (repository != "noah-l-frank/overte" or config.get("repository") != repository
            or config.get("repository_id") != 1319052603
            or config.get("trusted_actions_app_id") != 15368
            or config.get("validation_workflow") != "sync-validation.yml"):
        raise GateError("validation dispatch is outside the fixed native configuration")
    prefix = "repos/" + repository
    repo = api.json(prefix)
    branch = api.json(prefix + "/branches/main")
    workflow = api.json(prefix + "/actions/workflows/sync-validation.yml")
    if (not isinstance(repo, dict) or repo.get("id") != 1319052603
            or repo.get("full_name") != repository or repo.get("default_branch") != "main"
            or not isinstance(branch, dict) or branch.get("name") != "main" or branch.get("protected") is not True
            or not isinstance(branch.get("commit"), dict) or branch["commit"].get("sha") != checkout_source
            or not isinstance(workflow, dict) or workflow.get("id") != 350930895
            or workflow.get("path") != ".github/workflows/sync-validation.yml"
            or workflow.get("name") != "Sync validation" or workflow.get("state") != "active"):
        raise GateError("validation dispatch repository, protected source or workflow changed")
    return prefix


def _dispatch_run(value, run_id, source, correlation):
    prefix = "https://api.github.com/repos/noah-l-frank/overte"
    if (not isinstance(value, dict) or type(value.get("id")) is not int or value["id"] != run_id
            or type(value.get("workflow_id")) is not int or value["workflow_id"] != 350930895
            or type(value.get("run_attempt")) is not int or value["run_attempt"] != 1
            or type(value.get("check_suite_id")) is not int or value["check_suite_id"] <= 0
            or value.get("path") != ".github/workflows/sync-validation.yml"
            or value.get("event") != "workflow_dispatch" or value.get("head_branch") != "main"
            or value.get("head_sha") != source
            or value.get("display_title") != "Sync validation " + correlation
            or value.get("url") != prefix + "/actions/runs/" + str(run_id)
            or value.get("html_url") != "https://github.com/noah-l-frank/overte/actions/runs/" + str(run_id)
            or any(not isinstance(value.get(key), dict) or value[key].get("id") != 1319052603
                   or value[key].get("full_name") != "noah-l-frank/overte"
                   for key in ("repository", "head_repository"))
            or not isinstance(value.get("status"), str)
            or not (value.get("status") in {"queued", "in_progress", "waiting", "pending", "requested"}
                    and value.get("conclusion") is None or value.get("status") == "completed")):
        raise GateError("validation run identity or state differs from its own dispatch")
    return tuple(value[key] for key in ("id", "workflow_id", "check_suite_id", "path", "event",
                                       "head_branch", "head_sha", "run_attempt", "display_title", "url", "html_url"))


def _dispatch_native(api, prefix, run, source, correlation, identity):
    run_id = run["id"]
    attempt = api.json(f"{prefix}/actions/runs/{run_id}/attempts/1")
    if _dispatch_run(attempt, run_id, source, correlation) != identity:
        raise GateError("validation native attempt identity changed")
    suite = api.json(f"{prefix}/check-suites/{run['check_suite_id']}")
    if (not isinstance(suite, dict) or suite.get("id") != run["check_suite_id"]
            or suite.get("head_sha") != source or not isinstance(suite.get("app"), dict)
            or suite["app"].get("id") != 15368 or not isinstance(suite.get("repository"), dict)
            or suite["repository"].get("id") != 1319052603
            or suite.get("repository", {}).get("full_name") != "noah-l-frank/overte"):
        raise GateError("validation native suite or App differs")
    if run["status"] == "completed" and (attempt.get("status"), attempt.get("conclusion")) != ("completed", "success"):
        raise GateError("validation terminal native attempt did not succeed")


def dispatch_and_wait(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    gate_run_attempt = args.gate_run_attempt
    if gate_run_attempt is None:
        # Older workflow definitions still load this trusted code from main.
        try:
            gate_run_attempt = int(os.environ["GITHUB_RUN_ATTEMPT"])
        except (KeyError, ValueError) as error:
            raise GateError("gate run attempt must be an integer argument or GITHUB_RUN_ATTEMPT") from error
    if args.gate_run_id <= 0 or gate_run_attempt <= 0:
        raise GateError("gate run ID and attempt must be positive")
    api = GitHubApi()
    source = _dispatch_checkout_source()
    prefix = _dispatch_source(api, config, args.repository, source)
    # The PRT parent can still be running at PR H; the child executes main D.
    correlation = f"gate-{args.gate_run_id}-attempt-{gate_run_attempt}"
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
    dispatched = api.json(
        f"{prefix}/actions/workflows/{config['validation_workflow']}/dispatches",
        method="POST", fields=fields, dispatch_details=True,
    )
    if not isinstance(dispatched, dict) or type(dispatched.get("workflow_run_id")) is not int or dispatched["workflow_run_id"] <= 0:
        raise GateError("validation dispatch did not return a positive run ID; it must not be redispatched")
    run_id = dispatched["workflow_run_id"]
    run_endpoint = f"{prefix}/actions/runs/{run_id}"
    html_url = f"https://github.com/{args.repository}/actions/runs/{run_id}"
    if (dispatched.get("run_url") != "https://api.github.com/" + run_endpoint
            or dispatched.get("html_url") != html_url):
        raise GateError("validation dispatch returned foreign or malformed run URLs")
    deadline = time.monotonic() + args.timeout
    identity = None
    while time.monotonic() < deadline:
        run = api.json(run_endpoint)
        current = _dispatch_run(run, run_id, source, correlation)
        if identity is None:
            identity = current
            if run["status"] != "completed":
                _dispatch_native(api, prefix, run, source, correlation, identity)
        elif current != identity:
            raise GateError("validation run identity changed during monitoring")
        if run["status"] == "completed":
            if run.get("conclusion") != "success":
                raise GateError(f"{args.mode} validation did not succeed")
            _dispatch_native(api, prefix, run, source, correlation, identity)
            if _dispatch_checkout_source() != source:
                raise GateError("trusted dispatch checkout source changed")
            _dispatch_source(api, config, args.repository, source)
            final = api.json(run_endpoint)
            if (_dispatch_run(final, run_id, source, correlation) != identity
                    or (final.get("status"), final.get("conclusion")) != ("completed", "success")):
                raise GateError("validation terminal run changed during native source bookends")
            write_outputs(args.output, {"validation_run_id": run_id, "validation_url": html_url})
            return 0
        time.sleep(10)
    raise GateError("validation run did not reach a terminal success before timeout")


def cancel_redundant(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    wanted = set(config["redundant_pull_request_workflows"])
    if not wanted:
        # Older descendant workflows still call this trusted default-branch
        # helper with --window 60. Modern routing owns the selected executions;
        # an empty retired inventory needs neither API calls nor a polling wait.
        print("cancelled_redundant_runs=0")
        return 0
    api = GitHubApi()
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
    dispatch.add_argument("--gate-run-attempt", type=int,
                          help="gate attempt; defaults to GITHUB_RUN_ATTEMPT when omitted")
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
