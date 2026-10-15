#!/usr/bin/env python3
"""Dormant read-only GitHub adapter for producer.py; no dispatch or retry.

Only independently read API facts create Authenticated* protocol objects. This
first source contract supports same-fork PRs and local reusable workflows: API
referenced_workflows identifies the ORIGINAL merge/source, never head_sha or an
artifact assertion. Unknown sources, incomplete inventories and mixed attempts
cannot fall back to an older green. Trusted policy is supplied by the controller;
there is deliberately no candidate JSON/CLI policy or facts constructor.
An explicit, default-disabled manual-main contract separates trusted controller
source from independently materialized candidate receipts. Only original first
attempts are supported; rerun snapshots do not establish original execution.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import selectors
import shutil
import signal
import subprocess
import time
from urllib.parse import quote

import producer as P


REPOSITORY = "noah-l-frank/overte"
PREFIX = "repos/" + REPOSITORY
WORKFLOWS = frozenset(".github/workflows/" + name + ".yml" for name in (
    "project-tests", "parent-qualification", "sync-validation", "repository-checks"))
_SHA = re.compile(r"[0-9a-f]{40}\Z")
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")


class ApiError(P.ProtocolError):
    """Complete authenticated producer evidence is unavailable."""


class OriginalAttemptUnavailable(ApiError):
    """A rerun snapshot cannot authenticate its original producer executions."""


def require(condition, message):
    if not condition:
        raise ApiError(message)


def positive(value):
    require(type(value) is int and value > 0, "invalid positive API identity")
    return value


def sha(value):
    require(isinstance(value, str) and _SHA.fullmatch(value) and set(value) != {"0"}, "invalid immutable API SHA")
    return value


def _now():
    return datetime.now(timezone.utc)


class GitHubReadOnly:
    """Fixed github.com/fork GET boundary with deadlines and bounded pipes.

    gh follows its own authenticated archive redirect. No signed URL, token,
    stderr body, environment or arbitrary endpoint is returned in errors.
    """

    def _request(self, endpoint, maximum):
        require(isinstance(endpoint, str) and (endpoint == PREFIX or endpoint.startswith(PREFIX + "/"))
                and not re.search(r"[\x00-\x20\x7f]", endpoint) and ":" not in endpoint
                and ".." not in endpoint and "\\" not in endpoint, "GET endpoint is outside the reviewed fork")
        executable = shutil.which("gh")
        roots = (Path("/usr/bin"), Path("/usr/local/bin"), Path("/opt/hostedtoolcache"))
        try:
            require(executable is not None and Path(executable).is_absolute()
                    and any(Path(executable).is_relative_to(root) for root in roots),
                    "reviewed system GitHub CLI unavailable")
            resolved = Path(executable).resolve()
            require(any(resolved.is_relative_to(root) for root in roots), "reviewed system GitHub CLI unavailable")
        except (OSError, RuntimeError):
            raise ApiError("reviewed system GitHub CLI unavailable") from None
        command = [str(resolved), "api", "--hostname", "github.com", "--method", "GET",
                   "-H", "Accept: application/vnd.github+json", "-H", "X-GitHub-Api-Version: 2026-03-10", endpoint]
        process = None
        try:
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
            output = bytearray()
            deadline = time.monotonic() + 45
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ, True)
                selector.register(process.stderr, selectors.EVENT_READ, False)
                while selector.get_map():
                    remaining = deadline - time.monotonic()
                    require(remaining > 0, "GitHub GET deadline exceeded")
                    for key, _ in selector.select(min(remaining, 0.25)):
                        chunk = os.read(key.fileobj.fileno(), 65536)
                        if not chunk:
                            selector.unregister(key.fileobj)
                        elif key.data:
                            output.extend(chunk)
                            require(len(output) <= maximum, "GitHub GET response exceeds reviewed byte bound")
                        # Always drain stderr without storing or exposing it.
                require(process.wait(timeout=max(0.01, deadline - time.monotonic())) == 0,
                        "GitHub GET failed; response details withheld")
            return bytes(output)
        except (OSError, subprocess.SubprocessError):
            raise ApiError("GitHub GET unavailable; response details withheld") from None
        finally:
            if process is not None:
                if process.poll() is None:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    process.wait()
                for pipe in (process.stdout, process.stderr):
                    if pipe is not None:
                        pipe.close()

    def json(self, endpoint):
        def invalid_constant(value):
            raise ApiError("GitHub GET returned invalid bounded JSON")
        try:
            return json.loads(self._request(endpoint, 2_000_000), object_pairs_hook=P.inputs._unique_object,
                              parse_constant=invalid_constant)
        except (UnicodeError, ValueError) as error:
            if isinstance(error, ApiError):
                raise
            raise ApiError("GitHub GET returned invalid bounded JSON") from None

    def bytes(self, endpoint):
        return self._request(endpoint, P._MAX_ARCHIVE)


@dataclass(frozen=True)
class ManualSource:
    """Trusted review input, never a candidate manifest or activation setting.

    The immutable root tree binds the entire controller source, including files
    outside the explicit executable inventory. No real workflow is preapproved.
    """
    enabled: bool = False
    controller_commit: str = ""
    controller_tree: str = ""
    controller_path: str = ""
    sources: dict | None = None


def manual_identity(source):
    require(isinstance(source, ManualSource), "trusted manual source contract unavailable")
    return P.digest({"source_kind": "manual-main-v1", "controller_commit": source.controller_commit,
                     "controller_tree": source.controller_tree, "controller_path": source.controller_path,
                     "sources": source.sources})


@dataclass(frozen=True)
class AdapterPolicy:
    producer: P.Policy
    caller_workflow_id: int
    caller_path: str
    generations: dict[str, dict]
    publisher_job: str
    owner_jobs: dict[str, str]
    source_kind: str = "reusable-pr"
    manual: ManualSource | None = None


@dataclass(frozen=True)
class Snapshot:
    binding: dict
    references: dict
    observations: list[P.Observation]
    inventory_complete: bool
    unavailable: tuple[str, ...]
    source_chains: dict[int, dict]
    artifact_inventories: dict[int, list[dict]]


def _policy(value, plan, number):
    require(isinstance(value, AdapterPolicy), "trusted controller adapter policy required")
    P.policy_digest(value.producer)
    P.validate_plan(plan)
    positive(value.caller_workflow_id)
    require(isinstance(value.source_kind, str) and value.source_kind in {"reusable-pr", "manual-main-v1"},
            "unsupported producer source kind")
    if value.source_kind == "manual-main-v1":
        source = value.manual
        require(isinstance(source, ManualSource) and type(source.enabled) is bool and source.enabled,
                "manual producer source support is disabled")
        sha(source.controller_commit)
        sha(source.controller_tree)
        require(value.producer.events == ("workflow_dispatch",)
                and value.producer.workflow_ref == "refs/heads/main"
                and value.caller_path == value.producer.workflow_path
                and re.fullmatch(r"\.github/workflows/[a-z0-9-]+\.yml", value.caller_path)
                and value.generations == {}, "unsupported top-level manual source contract")
        require(isinstance(source.sources, dict) and 2 <= len(source.sources) <= 200
                and value.caller_path in source.sources and isinstance(source.controller_path, str)
                and source.controller_path in source.sources
                and source.controller_path.startswith("tools/test-evidence/")
                and source.controller_path.endswith(".py"), "complete manual controller inventory unavailable")
        for path, entry in source.sources.items():
            require(isinstance(path, str) and re.fullmatch(r"[A-Za-z0-9_./-]+", path)
                    and not any(part in {"", ".", "..", ".git"} for part in path.split("/")),
                    "unsafe manual controller source path")
            require(isinstance(entry, dict) and set(entry) == {"mode", "type", "sha"}
                    and entry["mode"] in {"100644", "100755"} and entry["type"] == "blob",
                    "invalid manual controller source entry")
            sha(entry["sha"])
        require(source.sources[value.caller_path]["mode"] == "100644"
                and source.sources[value.caller_path]["sha"] == value.producer.workflow_blob
                and value.producer.controller_digest == manual_identity(source),
                "manual controller identity differs from trusted producer policy")
    else:
        require(value.manual is None, "manual source cannot amend reusable-PR admission")
        _reusable_policy(value, number)
    require(isinstance(value.owner_jobs, dict) and set(value.owner_jobs) == set(plan["owners"])
            and all(isinstance(name, str) and name for name in [value.publisher_job, *value.owner_jobs.values()])
            and len({value.publisher_job, *value.owner_jobs.values()}) == 1 + len(value.owner_jobs),
            "trusted exact publisher/owner job names unavailable")


def _reusable_policy(value, number):
    require(value.producer.events == ("pull_request",)
            and value.producer.workflow_ref == f"refs/pull/{number}/merge"
            and value.producer.workflow_path == ".github/workflows/project-tests.yml"
            and value.caller_path == ".github/workflows/repository-checks.yml",
            "unsupported producer source-chain contract")
    require(isinstance(value.generations, dict) and bool(value.generations), "trusted complete generations unavailable")
    for name, workflows in value.generations.items():
        require(isinstance(name, str) and name and isinstance(workflows, dict) and set(workflows) == WORKFLOWS,
                "workflow generation must bind the complete reviewed tuple")
        for entry in workflows.values():
            require(isinstance(entry, dict) and set(entry) == {"mode", "type", "sha"}
                    and entry["mode"] == "100644" and entry["type"] == "blob", "invalid trusted workflow entry")
            sha(entry["sha"])


class Adapter:
    def __init__(self, api=None):
        self.api = api if api is not None else GitHubReadOnly()

    def _object(self, endpoint):
        value = self.api.json(PREFIX + ("/" + endpoint if endpoint else ""))
        require(isinstance(value, dict), "GitHub omitted a required API object")
        return value

    def _pages(self, endpoint, field, *, search=False):
        values, seen, expected = [], set(), None
        separator = "&" if "?" in endpoint else "?"
        for page in range(1, 11):
            value = self._object(endpoint + separator + f"per_page=100&page={page}")
            total, items = value.get("total_count"), value.get(field)
            require(type(total) is int and total >= 0 and isinstance(items, list) and len(items) <= 100
                    and (not search or total < 1000), "API search cap or incomplete paginated inventory")
            require(expected is None or total == expected, "API inventory changed during pagination")
            expected = total
            for item in items:
                require(isinstance(item, dict), "API page contains an invalid record")
                identity = positive(item.get("id"))
                require(identity not in seen, "API pagination repeats an identity")
                seen.add(identity)
            values.extend(items)
            require(len(values) <= expected, "API inventory exceeds its declared total")
            if len(values) == expected:
                return values
            if len(items) < 100:
                raise ApiError("API paginated inventory is incomplete")
        raise ApiError("API inventory exceeds reviewed pagination bound")

    def _ref(self, ref):
        value = self._object("git/ref/" + quote(ref, safe="/"))
        require(value.get("ref") == "refs/" + ref and value.get("object", {}).get("type") == "commit",
                "current Git ref identity unavailable")
        return sha(value["object"].get("sha"))

    def _commit(self, revision):
        value = self._object("git/commits/" + sha(revision))
        require(value.get("sha") == revision and isinstance(value.get("parents"), list)
                and all(isinstance(parent, dict) for parent in value["parents"]), "immutable commit identity mismatch")
        return sha(value.get("tree", {}).get("sha")), [sha(parent.get("sha")) for parent in value["parents"]]

    def current(self, number):
        positive(number)
        repository = self._object("")
        require(repository.get("full_name") == REPOSITORY and repository.get("id") == 1319052603,
                "repository API identity mismatch")
        pr = self._object(f"pulls/{number}")
        require(pr.get("number") == number and pr.get("state") == "open", "current open PR unavailable")
        for side in ("base", "head"):
            repo = pr.get(side, {}).get("repo", {})
            require(repo.get("full_name") == REPOSITORY and repo.get("id") == 1319052603,
                    "foreign-head source-chain contract is not implemented")
        base, head, merge = sha(pr["base"].get("sha")), sha(pr["head"].get("sha")), sha(pr.get("merge_commit_sha"))
        binding = {"repository": REPOSITORY, "repository_id": 1319052603, "pull_request": number,
                   "head_repository_id": pr["head"]["repo"]["id"], "base_ref": pr["base"].get("ref"),
                   "base_sha": base, "head_ref": pr["head"].get("ref"), "head_sha": head,
                   "merge_sha": merge, "merge_tree": "1" * 40, "merge_parents": [base, head]}
        P.validate_binding(binding)  # Validate ref spellings before constructing endpoints.
        default = repository.get("default_branch")
        require(isinstance(default, str) and default, "current default branch unavailable")
        P.validate_binding({**binding, "head_ref": default})
        references = {"base": self._ref("heads/" + binding["base_ref"]),
                      "head": self._ref("heads/" + binding["head_ref"]),
                      "merge": self._ref(f"pull/{number}/merge"), "default_ref": default,
                      "default": self._ref("heads/" + default)}
        require([references[key] for key in ("base", "head", "merge")] == [base, head, merge],
                "live PR and Git refs disagree")
        tree, parents = self._commit(merge)
        binding.update(merge_tree=tree, merge_parents=parents)
        return P.validate_binding(binding), references

    def _workflow_tuple(self, revision):
        tree, parents = self._commit(revision)
        cursor = tree
        for directory in (".github", "workflows"):
            value = self._object("git/trees/" + cursor)
            require(value.get("sha") == cursor and value.get("truncated") is False and isinstance(value.get("tree"), list)
                    and all(isinstance(entry, dict) for entry in value["tree"]),
                    "immutable workflow tree is unavailable or truncated")
            found = [entry for entry in value["tree"] if entry.get("path") == directory]
            require(len(found) == 1 and found[0].get("mode") == "040000" and found[0].get("type") == "tree",
                    "workflow directory is missing or aliased")
            cursor = sha(found[0].get("sha"))
        value = self._object("git/trees/" + cursor)
        require(value.get("sha") == cursor and value.get("truncated") is False and isinstance(value.get("tree"), list)
                and all(isinstance(entry, dict) for entry in value["tree"]),
                "immutable workflow inventory is unavailable or truncated")
        workflows = {}
        for path in WORKFLOWS:
            found = [entry for entry in value["tree"] if entry.get("path") == path.rsplit("/", 1)[1]]
            require(len(found) == 1, "complete caller generation is missing or ambiguous")
            workflows[path] = {key: found[0].get(key) for key in ("mode", "type", "sha")}
        return tree, parents, workflows

    def _chain(self, run, policy, binding):
        require(run.get("repository", {}).get("id") == 1319052603
                and run.get("repository", {}).get("full_name") == REPOSITORY
                and run.get("head_repository", {}).get("id") == binding["head_repository_id"]
                and run.get("head_repository", {}).get("full_name") == REPOSITORY
                and run.get("workflow_id") == policy.caller_workflow_id
                and run.get("path") == policy.caller_path and run.get("event") == "pull_request"
                and run.get("head_sha") == binding["head_sha"] and run.get("head_branch") == binding["head_ref"],
                "run repository/caller/head identity mismatch")
        associated = run.get("pull_requests")
        require(isinstance(associated, list) and sum(isinstance(item, dict) and item.get("number") == binding["pull_request"]
                                                    for item in associated) == 1,
                "run's independently associated PR is missing or ambiguous")
        references = run.get("referenced_workflows")
        require(isinstance(references, list), "original reusable source chain unavailable")
        prefix = REPOSITORY + "/" + policy.producer.workflow_path + "@"
        matches = [item for item in references if isinstance(item, dict) and str(item.get("path", "")).startswith(prefix)]
        require(len(matches) == 1, "original reusable producer source is missing or ambiguous")
        source = matches[0]
        revision = sha(source.get("sha"))
        require(source.get("path") == prefix + revision and source.get("ref") == policy.producer.workflow_ref,
                "producer source is not the independently observed local PR merge")
        tree, parents, workflows = self._workflow_tuple(revision)
        matching = [name for name, expected in policy.generations.items() if workflows == expected]
        require(len(matching) == 1 and workflows[policy.producer.workflow_path]["sha"] == policy.producer.workflow_blob,
                "original caller/producer workflow generation is unknown or mixed")
        require(revision == binding["merge_sha"] and tree == binding["merge_tree"] and parents == binding["merge_parents"],
                "original producer candidate differs from the current exact PR merge")
        # Verify every local reusable reference against the SAME independently
        # observed merge. A foreign/remote/other-generation reference is unknown.
        for item in references:
            require(isinstance(item, dict) and item.get("sha") == revision
                    and item.get("ref") == policy.producer.workflow_ref
                    and isinstance(item.get("path"), str)
                    and item["path"].startswith(REPOSITORY + "/.github/workflows/")
                    and item["path"].endswith("@" + revision), "unsupported referenced workflow chain")
        return {"caller_path": policy.caller_path, "caller_blob": workflows[policy.caller_path]["sha"],
                "caller_commit": revision, "producer_path": policy.producer.workflow_path,
                "producer_blob": workflows[policy.producer.workflow_path]["sha"], "producer_commit": revision,
                "producer_ref": source["ref"], "generation": matching[0]}

    def _manual_chain(self, run, policy, references):
        source = policy.manual
        require(references["default_ref"] == "main" and references["default"] == source.controller_commit,
                "manual controller is not current trusted main")
        for key in ("repository", "head_repository"):
            require(run.get(key, {}).get("id") == 1319052603
                    and run.get(key, {}).get("full_name") == REPOSITORY, "manual run repository mismatch")
        require(run.get("workflow_id") == policy.caller_workflow_id
                and run.get("path") in {policy.caller_path, policy.caller_path + "@main"}
                and run.get("event") == "workflow_dispatch" and run.get("head_branch") == "main"
                and run.get("head_sha") == source.controller_commit
                and run.get("pull_requests") == [] and run.get("referenced_workflows") == [],
                "manual run is not the exact trusted top-level main controller")
        tree, _ = self._commit(source.controller_commit)
        require(tree == source.controller_tree, "manual controller root tree mismatch")
        # Read immutable directory objects, never candidate-provided files or an
        # assumed workflow path. The pinned root covers the complete source tree.
        directories = {}
        for path, expected in source.sources.items():
            cursor = tree
            parts = path.split("/")
            for index, part in enumerate(parts):
                if cursor not in directories:
                    value = self._object("git/trees/" + cursor)
                    require(value.get("sha") == cursor and value.get("truncated") is False
                            and isinstance(value.get("tree"), list)
                            and all(isinstance(entry, dict) for entry in value["tree"]),
                            "complete manual controller source tree unavailable")
                    directories[cursor] = value["tree"]
                found = [entry for entry in directories[cursor] if entry.get("path") == part]
                require(len(found) == 1, "manual controller source is missing or ambiguous")
                entry = {key: found[0].get(key) for key in ("mode", "type", "sha")}
                if index == len(parts) - 1:
                    require(entry == expected, "manual workflow/controller source differs from trusted review")
                else:
                    require(entry["mode"] == "040000" and entry["type"] == "tree",
                            "manual controller source directory is aliased")
                    cursor = sha(entry["sha"])
        return {"source_kind": policy.source_kind, "caller_path": policy.caller_path,
                "caller_blob": source.sources[policy.caller_path]["sha"], "caller_commit": source.controller_commit,
                "producer_path": policy.producer.workflow_path, "producer_blob": policy.producer.workflow_blob,
                "producer_commit": source.controller_commit, "producer_ref": "refs/heads/main",
                "controller_tree": tree, "controller_identity": manual_identity(source)}

    def _manual_job(self, value, run, app_id):
        # Attempt-specific inventories alone can be snapshot rows on reruns.
        # Only an independently bookended first-ever attempt is supported here.
        require(run["run_attempt"] == 1 and type(value.get("run_attempt", 1)) is int
                and value.get("run_attempt", 1) == 1,
                "manual job is not an original first-attempt execution")
        identity = positive(value.get("id"))
        detail = self._object(f"actions/jobs/{identity}")
        fields = ("id", "run_id", "head_sha", "name", "status", "conclusion",
                  "started_at", "completed_at", "check_run_url")
        require(all(detail.get(key) == value.get(key) for key in fields)
                and type(detail.get("run_attempt", 1)) is int and detail.get("run_attempt", 1) == 1,
                "original manual job identity changed or unavailable")
        # Missing run_attempt is allowed only because first-ever run attempt 1
        # has no prior execution to relay. No timestamp supplies this identity.
        return self._job({**detail, "run_attempt": 1}, run, app_id)

    def _job(self, value, run, app_id):
        require(value.get("run_id") == run["id"] and value.get("run_attempt") == run["run_attempt"]
                and value.get("head_sha") == run["head_sha"], "mixed or foreign job attempt")
        identity = positive(value.get("id"))
        require(value.get("check_run_url") == f"https://api.github.com/{PREFIX}/check-runs/{identity}",
                "job check-run source is unavailable")
        check = self._object(f"check-runs/{identity}")
        require(check.get("id") == identity and check.get("head_sha") == run["head_sha"]
                and check.get("check_suite", {}).get("id") == run["check_suite_id"]
                and check.get("app", {}).get("id") == app_id, "job check app/suite identity mismatch")
        return P.AuthenticatedJob(identity, value["run_attempt"], value.get("status"), value.get("conclusion"),
                                  value.get("started_at"), value.get("completed_at"))

    def _artifacts(self, run):
        return self._pages(f"actions/runs/{run.run_id}/artifacts", "artifacts")

    def _artifact(self, run, kind, items, now, head_sha):
        name = f"ci-{kind}-{run.run_id}-{run.attempt}"
        selected = [item for item in items if item.get("name") == name]
        if not selected:
            return None, None
        require(len(selected) == 1, "producer artifact name is reused or ambiguous")
        item = selected[0]
        detail = self._object(f"actions/artifacts/{positive(item.get('id'))}")
        keys = ("id", "name", "digest", "size_in_bytes", "expired", "created_at", "expires_at", "workflow_run")
        require(all(detail.get(key) == item.get(key) for key in keys), "artifact inventory/detail changed")
        owner = detail.get("workflow_run", {})
        require(owner.get("id") == run.run_id and owner.get("repository_id") == 1319052603
                and owner.get("head_repository_id") == 1319052603
                and owner.get("head_sha") == head_sha
                and isinstance(detail.get("digest"), str) and _DIGEST.fullmatch(detail["digest"])
                and type(detail.get("size_in_bytes")) is int and 0 < detail["size_in_bytes"] <= P._MAX_ARCHIVE,
                "artifact source or bounded API digest unavailable")
        facts = P.AuthenticatedArtifact(detail["id"], owner["repository_id"], owner["id"], detail["name"],
                                         detail["digest"], detail.get("expired"), detail.get("created_at"),
                                         detail.get("expires_at"), True, 1)
        raw = self.api.bytes(PREFIX + f"/actions/artifacts/{facts.artifact_id}/zip")
        require(isinstance(raw, bytes) and len(raw) == detail["size_in_bytes"], "raw artifact size differs from API")
        P.read_artifact(raw, kind, facts, run, now=now)
        return raw, facts

    def _observation(self, listed, policy, binding, now, references=None):
        identity = positive(listed.get("id"))
        latest = self._object(f"actions/runs/{identity}")
        latest_attempt = positive(latest.get("run_attempt"))
        manual = policy.source_kind == "manual-main-v1"
        if manual and latest_attempt != 1:
            raise OriginalAttemptUnavailable("manual rerun original execution provenance is unsupported")
        attempt = self._object(f"actions/runs/{identity}/attempts/{latest_attempt}")
        fields = ("id", "workflow_id", "check_suite_id", "path", "event", "head_sha", "head_branch", "run_attempt", "status", "conclusion")
        if manual:
            fields += ("repository", "head_repository", "pull_requests", "referenced_workflows", "run_started_at")
        require(all(listed.get(key) == latest.get(key) == attempt.get(key) for key in fields),
                "latest run/attempt inventory changed or mixed")
        chain = (self._manual_chain(attempt, policy, references) if manual
                 else self._chain(attempt, policy, binding))
        source_head = attempt["head_sha"]
        suite = self._object(f"check-suites/{positive(attempt.get('check_suite_id'))}")
        require(suite.get("id") == attempt["check_suite_id"] and suite.get("head_sha") == source_head
                and suite.get("repository", {}).get("id") == 1319052603
                and suite.get("app", {}).get("id") == policy.producer.actions_app_id,
                "run check-suite/app authority mismatch")
        jobs = self._pages(f"actions/runs/{identity}/attempts/{latest_attempt}/jobs", "jobs")
        require(all(job.get("run_id") == identity
                    and (job.get("run_attempt", 1) if manual else job.get("run_attempt")) == latest_attempt for job in jobs),
                "latest-attempt job snapshot contains mixed executions")
        by_name = {}
        for job in jobs:
            by_name.setdefault(job.get("name"), []).append(job)
        selected = {}
        for name in [policy.publisher_job, *policy.owner_jobs.values()]:
            require(len(by_name.get(name, [])) <= 1, "selected job name is ambiguous")
            authenticate = self._manual_job if manual else self._job
            selected[name] = authenticate(by_name[name][0], attempt, policy.producer.actions_app_id) if name in by_name else None
        run = P.AuthenticatedRun(REPOSITORY, 1319052603, suite["app"]["id"], identity, latest_attempt, latest_attempt,
                                 attempt.get("run_started_at"), policy.producer.workflow_path, chain["producer_blob"],
                                 chain["producer_commit"], chain["producer_ref"], attempt["event"], attempt["status"],
                                 attempt.get("conclusion"), selected[policy.publisher_job],
                                 {name: selected[job] for name, job in policy.owner_jobs.items() if selected[job] is not None})
        P._run(run, policy.producer)
        if manual:
            chain.update(original_attempt=1, publisher_job_id=run.publisher.job_id if run.publisher else None,
                         owner_job_ids={name: job.job_id for name, job in run.owners.items()})
        items = self._artifacts(run)
        raw, facts = self._artifact(run, "descriptor", items, now, source_head)
        return P.Observation(run, raw, facts), chain, items

    def capture(self, number, plan, policy, *, now=None):
        """Return a bookended complete API snapshot, or explicit no-reuse gaps."""
        now = now if now is not None else _now()
        P._now(now)
        _policy(policy, plan, number)
        binding, references = self.current(number)
        if policy.source_kind == "manual-main-v1":
            require(references["default_ref"] == "main" and references["default"] == policy.manual.controller_commit,
                    "manual controller is not current trusted main")
        endpoint = f"actions/workflows/{policy.caller_workflow_id}/runs?head_sha="
        endpoint += (policy.manual.controller_commit + "&event=workflow_dispatch&branch=main"
                     if policy.source_kind == "manual-main-v1" else binding["head_sha"])
        observations, chains, inventories, unavailable = [], {}, {}, []
        try:
            listed = self._pages(endpoint, "workflow_runs", search=True)
            for item in listed:
                try:
                    observation, chain, artifacts = self._observation(item, policy, binding, now, references)
                    observations.append(observation)
                    chains[observation.run.run_id] = chain
                    inventories[observation.run.run_id] = artifacts
                except OriginalAttemptUnavailable:
                    unavailable.append("manual-original-attempt-unavailable")
                except (ApiError, P.ProtocolError, KeyError, TypeError, ValueError):
                    unavailable.append("run-source-or-proof-unclassified")
            final_list = self._pages(endpoint, "workflow_runs", search=True)
            fields = ("id", "run_attempt", "status", "conclusion", "run_started_at", "updated_at")
            require([{key: row.get(key) for key in fields} for row in listed]
                    == [{key: row.get(key) for key in fields} for row in final_list], "authority inventory changed")
        except (ApiError, KeyError, TypeError, ValueError):
            unavailable.append("run-inventory-incomplete-or-changed")
        final_binding, final_refs = self.current(number)
        require(final_binding == binding and final_refs == references, "current PR or refs changed during API snapshot")
        return Snapshot(binding, references, observations, not unavailable, tuple(sorted(set(unavailable))), chains, inventories)

    def verify(self, number, plan, policy, contexts, *, clock=_now):
        """Read both snapshots and validate original aggregate; no implicit rerun."""
        initial = self.capture(number, plan, policy, now=clock())
        authority = P.select_authority(initial.observations, initial.binding, plan, policy.producer,
                                       inventory_complete=initial.inventory_complete, now=clock())
        require(authority["state"] == "proof-required", "newest producer is absent, pending, failed or unresolved")
        selected = next(item for item in initial.observations if item.run.run_id == authority["run_id"])
        artifacts = initial.artifact_inventories[selected.run.run_id]
        source_head = (policy.manual.controller_commit if policy.source_kind == "manual-main-v1"
                       else initial.binding["head_sha"])
        raw, artifact = self._artifact(selected.run, "aggregate", artifacts, clock(), source_head)
        require(raw is not None and artifact is not None, "newest aggregate proof is missing")
        final = self.capture(number, plan, policy, now=clock())
        require(initial.references == final.references, "current refs changed during aggregate verification")
        if policy.source_kind == "manual-main-v1":
            require(initial.source_chains.get(selected.run.run_id) == final.source_chains.get(selected.run.run_id),
                    "manual original source/job provenance changed during verification")
        # Artifacts authenticate a run, not a publishing job. Retain the complete
        # independently read final inventory too: a new duplicate, deletion or
        # replacement must not leave the initially downloaded aggregate usable.
        initial_items = [item for item in artifacts if item.get("name") == artifact.name]
        final_items = [item for item in final.artifact_inventories.get(selected.run.run_id, [])
                       if item.get("name") == artifact.name]
        require(len(initial_items) == len(final_items) == 1 and initial_items == final_items,
                "aggregate artifact inventory changed during verification")
        value = P.verify_aggregate(raw, artifact, initial.binding, plan, policy.producer, initial.observations,
                                   inventory_complete=initial.inventory_complete, final_binding=final.binding,
                                   final_observations=final.observations, final_inventory_complete=final.inventory_complete,
                                   contexts=contexts, now=clock())
        if policy.source_kind == "manual-main-v1":
            # Ordinary execution receipts do not prove protected publication
            # after a parent-owned kernel scope is independently empty. Source
            # admission is groundwork, not a policy-toggle authorization to reuse.
            raise ApiError("manual protected post-kill receipt verification is not implemented")
        return {**value, "source_chain": final.source_chains[value["run_id"]]}
