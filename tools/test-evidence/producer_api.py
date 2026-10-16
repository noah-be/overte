#!/usr/bin/env python3
"""Dormant read-only GitHub adapter for producer.py; no dispatch or retry.

Only independently read API facts create Authenticated* protocol objects. The
separate source contracts support open same-fork PRs and integrated source lookup: API
referenced_workflows identifies the ORIGINAL merge/source, never head_sha or an
artifact assertion. Unknown sources, incomplete inventories and mixed attempts
cannot fall back to an older green. Trusted policy is supplied by the controller;
there is deliberately no candidate JSON/CLI policy or facts constructor.
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
PROTECTED_PUSH_WORKFLOWS = {
    350930890: (".github/workflows/parent-qualification.yml",
                frozenset({"main", "android-main", "android-vr", "apple-main"})),
    330551824: (".github/workflows/project-tests.yml",
                frozenset({"android-phone", "android-vr-pico", "apple-ios"})),
}
_SHA = re.compile(r"[0-9a-f]{40}\Z")
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")


class ApiError(P.ProtocolError):
    """Complete authenticated producer evidence is unavailable."""


class OriginalAttemptUnavailable(ApiError):
    """A rerun snapshot cannot authenticate original successful execution."""


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

    def _request(self, endpoint, maximum, *, api_version="2026-03-10"):
        require(isinstance(endpoint, str) and (endpoint == PREFIX or endpoint.startswith(PREFIX + "/"))
                and not re.search(r"[\x00-\x20\x7f]", endpoint) and ":" not in endpoint
                and ".." not in endpoint and "\\" not in endpoint, "GET endpoint is outside the reviewed fork")
        require(api_version == "2026-03-10" or api_version == "2022-11-28"
                and re.fullmatch(re.escape(PREFIX) + r"/pulls/[1-9][0-9]*", endpoint) is not None,
                "GET API version is outside the reviewed endpoint contract")
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
                   "-H", "Accept: application/vnd.github+json", "-H", "X-GitHub-Api-Version: " + api_version, endpoint]
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

    def _json(self, raw):
        def invalid_constant(value):
            raise ApiError("GitHub GET returned invalid bounded JSON")
        try:
            return json.loads(raw, object_pairs_hook=P.inputs._unique_object,
                              parse_constant=invalid_constant)
        except (UnicodeError, ValueError) as error:
            if isinstance(error, ApiError):
                raise
            raise ApiError("GitHub GET returned invalid bounded JSON") from None

    def json(self, endpoint):
        return self._json(self._request(endpoint, 2_000_000))

    def integrated_pr(self, number):
        # 2026-03-10 removed merge_commit_sha. This independently versioned
        # full-PR read is fixed, explicit and has no unversioned fallback.
        endpoint = PREFIX + f"/pulls/{positive(number)}"
        return self._json(self._request(endpoint, 2_000_000, api_version="2022-11-28"))

    def bytes(self, endpoint):
        return self._request(endpoint, P._MAX_ARCHIVE)

    def immutable_tree(self, tree_sha):
        """Bounded complete source inventory; no archive or materialized code.

        Overte's full tree exceeds the small metadata response bound. The
        independently authenticated immutable tree endpoint alone gets 20MB.
        Truncation and entry structure must still be rejected by the consumer.
        """
        return self._json(self._request(PREFIX + '/git/trees/' + sha(tree_sha) + '?recursive=1', 20_000_000))


@dataclass(frozen=True)
class AdapterPolicy:
    producer: P.Policy
    caller_workflow_id: int
    caller_path: str
    generations: dict[str, dict]
    publisher_job: str
    owner_jobs: dict[str, str]
    final_publisher_prefix: str


@dataclass(frozen=True)
class Snapshot:
    binding: dict
    references: dict
    observations: list[P.Observation]
    inventory_complete: bool
    unavailable: tuple[str, ...]
    source_chains: dict[int, dict]
    artifact_inventories: dict[int, list[dict]]
    other_candidates: dict[int, dict]


def _policy(value, plan, number):
    require(isinstance(value, AdapterPolicy), "trusted controller adapter policy required")
    P.policy_digest(value.producer)
    P.validate_plan(plan)
    positive(value.caller_workflow_id)
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
    require(isinstance(value.owner_jobs, dict) and set(value.owner_jobs) == set(plan["owners"])
            and all(isinstance(name, str) and name for name in [value.publisher_job, *value.owner_jobs.values()])
            and len({value.publisher_job, *value.owner_jobs.values()}) == 1 + len(value.owner_jobs),
            "trusted exact publisher/owner job names unavailable")
    require(isinstance(value.final_publisher_prefix, str) and 0 < len(value.final_publisher_prefix) <= 200
            and not re.search(r"[\x00-\x1f\x7f]", value.final_publisher_prefix)
            and not any(name.startswith(value.final_publisher_prefix)
                        for name in [value.publisher_job, *value.owner_jobs.values()]),
            "trusted distinct final publisher prefix unavailable")


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

    def _associated_prs(self, revision):
        """The commit association API returns arrays, without an Actions total."""
        values, seen = [], set()
        for page in range(1, 11):
            items = self.api.json(f"{PREFIX}/commits/{sha(revision)}/pulls?per_page=100&page={page}")
            require(isinstance(items, list) and len(items) <= 100, "merged PR association inventory unavailable")
            for item in items:
                require(isinstance(item, dict), "invalid merged PR association")
                identity = positive(item.get("id"))
                positive(item.get("number"))
                require(identity not in seen, "merged PR association repeats an identity")
                seen.add(identity)
            values.extend(items)
            if len(items) < 100:
                return values
        raise ApiError("merged PR association exceeds reviewed pagination bound")

    def _introduced_pr(self, revision, now):
        """Classify every actual association; only its introducer supplies proof.

        Non-default commits may also be associated with open/downstream PRs.
        Their existence is not ambiguity about which PR actually merged here.
        """
        introduced, facts = [], []
        for summary in self._associated_prs(revision):
            number = positive(summary.get("number"))
            pr = self.api.integrated_pr(number)
            require(isinstance(pr, dict) and all(key in pr for key in (
                "id", "number", "state", "base", "head", "merged", "merge_commit_sha", "merged_at", "closed_at")),
                "versioned full PR identity is unavailable")
            identity = {}
            for value in (summary, pr):
                current = {"id": positive(value.get("id")), "number": positive(value.get("number")),
                           "state": value.get("state")}
                require(current["state"] in {"open", "closed"}, "associated PR state is unknown")
                for side in ("base", "head"):
                    branch = value.get(side)
                    repo = branch.get("repo") if isinstance(branch, dict) else None
                    require(isinstance(repo, dict) and repo.get("id") == 1319052603
                            and repo.get("full_name") == REPOSITORY,
                            "associated PR repository is outside the same-fork contract")
                    ref = branch.get("ref")
                    require(isinstance(ref, str) and 0 < len(ref) <= 255
                            and re.search(r"[\x00-\x20\x7f]", ref) is None,
                            "associated PR ref identity is unavailable")
                    current[side] = {"ref": ref, "sha": sha(branch.get("sha")),
                                     "repository_id": repo["id"], "repository": repo["full_name"]}
                require(not identity or identity == current, "associated PR summary/full identity differs")
                identity = current
            require(type(pr["merged"]) is bool, "associated PR merged state is unavailable")
            merge = pr["merge_commit_sha"]
            if merge is not None:
                sha(merge)
            # No summary field is required that the 2026 API actually omits.
            # A contradictory optional claim still cannot be silently ignored.
            require(all(key not in summary or summary[key] == pr[key]
                        for key in ("merged", "merge_commit_sha", "merged_at", "closed_at")),
                    "associated PR summary/full merge facts differ")
            if pr["state"] == "open":
                require(pr["merged"] is False and pr["merged_at"] is None and pr["closed_at"] is None,
                        "open associated PR has contradictory merge facts")
            else:
                closed = P._time(pr["closed_at"])
                require(closed <= now, "associated PR close is in the future")
                if pr["merged"]:
                    require(merge is not None and P._time(pr["merged_at"]) <= closed,
                            "merged associated PR commit/time is unavailable")
                else:
                    require(pr["merged_at"] is None, "unmerged associated PR has a merge time")
            introduces = merge == revision
            require(not introduces or pr["state"] == "closed" and pr["merged"] is True,
                    "associated PR contradicts the actual protected integration")
            if introduces:
                introduced.append(pr)
            facts.append({**identity, **{key: pr[key] for key in
                          ("merged", "merge_commit_sha", "merged_at", "closed_at")},
                          "classification": "introducer" if introduces else "known-nonintroducer"})
        require(len(introduced) == 1, "integrated source introducer PR is missing or ambiguous")
        return introduced[0], sorted(facts, key=lambda value: value["id"])

    def _integrated_current(self, push_run_id, app_id, now):
        """Authenticate a normal current protected push without a topic ref.

        This is provenance for looking up an ORIGINAL PR candidate. It is not a
        receipt for executing the push commit or admission across a sync edge.
        """
        positive(push_run_id); positive(app_id)
        repository = self._object("")
        require(repository.get("id") == 1319052603 and repository.get("full_name") == REPOSITORY
                and repository.get("default_branch") == "main", "integrated repository identity changed")
        latest = self._object(f"actions/runs/{push_run_id}")
        require(positive(latest.get("run_attempt")) == 1, "protected push original attempt unavailable")
        run = self._object(f"actions/runs/{push_run_id}/attempts/1")
        fields = ("id", "workflow_id", "check_suite_id", "event", "path", "head_sha", "head_branch",
                  "run_attempt", "status", "conclusion", "run_started_at")
        require(all(run.get(key) == latest.get(key) for key in fields) and run.get("id") == push_run_id
                and run.get("event") == "push" and type(run.get("workflow_id")) is int
                and run["workflow_id"] in PROTECTED_PUSH_WORKFLOWS,
                "protected push run/attempt identity unavailable")
        for key in ("repository", "head_repository"):
            value = run.get(key)
            require(isinstance(value, dict) and value.get("id") == 1319052603
                    and value.get("full_name") == REPOSITORY, "protected push repository mismatch")
        path, branches = PROTECTED_PUSH_WORKFLOWS[run["workflow_id"]]
        target, revision = run.get("head_branch"), sha(run.get("head_sha"))
        require(target in branches and run.get("path") == path
                and run.get("status") in P._PENDING | {"completed"}
                and (run.get("status") == "completed" and run.get("conclusion") == "success"
                     or run.get("status") in P._PENDING and run.get("conclusion") is None),
                "protected push source/status unavailable")
        workflow = self._object(f"actions/workflows/{run['workflow_id']}")
        require(workflow.get("id") == run["workflow_id"] and workflow.get("path") == path,
                "protected push workflow registration changed")
        branch = self._object("branches/" + quote(target, safe=""))
        require(branch.get("name") == target and branch.get("protected") is True
                and branch.get("commit", {}).get("sha") == revision
                and self._ref("heads/" + target) == revision, "protected push is not the exact current target")
        suite = self._object(f"check-suites/{positive(run.get('check_suite_id'))}")
        require(suite.get("id") == run["check_suite_id"] and suite.get("head_sha") == revision
                and suite.get("repository", {}).get("id") == 1319052603
                and suite.get("app", {}).get("id") == app_id, "protected push check-suite/app mismatch")
        tree, parents = self._commit(revision)
        require(len(parents) == 2, "integrated source requires a normal two-parent PR merge")
        pr, associations = self._introduced_pr(revision, now)
        number = positive(pr["number"])
        merged = P._time(pr.get("merged_at"))
        require(merged <= P._time(pr.get("closed_at")) <= now
                and merged <= P._time(run.get("run_started_at")) <= now,
                "integrated PR/push chronology unavailable")
        binding = {"repository": REPOSITORY, "repository_id": 1319052603, "pull_request": number,
                   "head_repository_id": 1319052603, "base_ref": pr["base"].get("ref"),
                   "base_sha": sha(pr["base"].get("sha")), "head_ref": pr["head"].get("ref"),
                   "head_sha": sha(pr["head"].get("sha")), "merge_sha": revision,
                   "merge_tree": tree, "merge_parents": parents}
        P.validate_binding(binding)
        require(binding["base_ref"] == target, "merged PR targets a different protected branch")
        integration = {"push_run_id": push_run_id, "push_attempt": 1, "workflow_id": run["workflow_id"],
                       "workflow_path": path, "target": target, "commit": revision, "tree": tree,
                       "parents": parents, "pull_request": number, "pr_id": pr["id"],
                       "merged_at": pr["merged_at"], "closed_at": pr["closed_at"],
                       "push_status": run["status"], "push_conclusion": run.get("conclusion")}
        references = {"integration": integration, "associated_prs": associations,
                      "target": revision, "default_ref": "main",
                      "default": self._ref("heads/main")}
        return binding, references

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
        base, head = sha(pr["base"].get("sha")), sha(pr["head"].get("sha"))
        # Resolve the live synthetic merge without relying on the PR payload's
        # merge_commit_sha. Bind the result to independent immutable commit
        # facts and current base/head refs before accepting its identity.
        merge_commit = self._object(f"commits/refs/pull/{number}/merge")
        merge = sha(merge_commit.get("sha"))
        require(isinstance(merge_commit.get("commit"), dict)
                and isinstance(merge_commit.get("parents"), list)
                and all(isinstance(parent, dict) for parent in merge_commit["parents"]),
                "current PR merge commit is unavailable")
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
                      "merge": merge, "default_ref": default,
                      "default": self._ref("heads/" + default)}
        require([references[key] for key in ("base", "head", "merge")] == [base, head, merge],
                "live PR and Git refs disagree")
        tree, parents = self._commit(merge)
        require(merge_commit["commit"].get("tree", {}).get("sha") == tree
                and [parent.get("sha") for parent in merge_commit["parents"]] == parents == [base, head],
                "current PR merge ref differs from its immutable ordered parents/tree")
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

    def _chain(self, run, policy, binding, *, integrated=False):
        require(run.get("repository", {}).get("id") == 1319052603
                and run.get("repository", {}).get("full_name") == REPOSITORY
                and run.get("head_repository", {}).get("id") == binding["head_repository_id"]
                and run.get("head_repository", {}).get("full_name") == REPOSITORY
                and run.get("workflow_id") == policy.caller_workflow_id
                and run.get("path") == policy.caller_path and run.get("event") == "pull_request"
                and run.get("head_sha") == binding["head_sha"] and run.get("head_branch") == binding["head_ref"],
                "run repository/caller/head identity mismatch")
        associated = run.get("pull_requests")
        require(isinstance(associated, list) and (
            integrated and (not associated or len(associated) == 1 and isinstance(associated[0], dict)
                            and associated[0].get("number") == binding["pull_request"])
            or not integrated and sum(isinstance(item, dict) and item.get("number") == binding["pull_request"]
                                      for item in associated) == 1),
                "run's independently associated PR is missing or ambiguous")
        # Closed same-fork runs legitimately lose this API array. Only the
        # separate integrated path has independently authenticated the unique
        # merged PR; its exact original ref and immutable parents/tree below
        # must still bind the source. OPEN association requirements are intact.
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
        require(len(parents) == 2 and parents[1] == binding["head_sha"],
                "original producer has unknown ordered PR parents")
        if revision == binding["merge_sha"]:
            require(tree == binding["merge_tree"] and parents == binding["merge_parents"],
                    "current producer source tree/parents differ from independently read candidate")
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
                "producer_ref": source["ref"], "generation": matching[0],
                "candidate": {"merge_sha": revision, "merge_tree": tree, "merge_parents": parents}}

    def _job(self, value, run, app_id, *, final_name=None):
        require(value.get("run_id") == run["id"] and value.get("run_attempt") == run["run_attempt"]
                and value.get("head_sha") == run["head_sha"], "mixed or foreign job attempt")
        identity = positive(value.get("id"))
        require(value.get("check_run_url") == f"https://api.github.com/{PREFIX}/check-runs/{identity}",
                "job check-run source is unavailable")
        check = self._object(f"check-runs/{identity}")
        require(check.get("id") == identity and check.get("head_sha") == run["head_sha"]
                and check.get("check_suite", {}).get("id") == run["check_suite_id"]
                and check.get("app", {}).get("id") == app_id, "job check app/suite identity mismatch")
        if final_name is not None:
            require(value.get("name") == check.get("name") == final_name
                    and all(value.get(key) == check.get(key) for key in
                            ("status", "conclusion", "started_at", "completed_at")),
                    "final publisher native job/check commitment differs")
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

    def _observation(self, listed, policy, binding, now, *, integrated=False):
        identity = positive(listed.get("id"))
        latest = self._object(f"actions/runs/{identity}")
        latest_attempt = positive(latest.get("run_attempt"))
        # Failed-only retries can carry old successful timestamps under NEW job
        # IDs and run_attempt fields. Do not infer original execution from them.
        if latest_attempt != 1:
            raise OriginalAttemptUnavailable("original first-attempt producer source unavailable")
        attempt = self._object(f"actions/runs/{identity}/attempts/{latest_attempt}")
        fields = ("id", "workflow_id", "check_suite_id", "path", "event", "head_sha", "head_branch", "run_attempt", "status", "conclusion")
        require(all(listed.get(key) == latest.get(key) == attempt.get(key) for key in fields),
                "latest run/attempt inventory changed or mixed")
        chain = self._chain(attempt, policy, binding, integrated=integrated)
        suite = self._object(f"check-suites/{positive(attempt.get('check_suite_id'))}")
        require(suite.get("id") == attempt["check_suite_id"] and suite.get("head_sha") == binding["head_sha"]
                and suite.get("repository", {}).get("id") == 1319052603
                and suite.get("app", {}).get("id") == policy.producer.actions_app_id,
                "run check-suite/app authority mismatch")
        source_run = P.AuthenticatedRun(REPOSITORY, 1319052603, suite["app"]["id"], identity, 1, 1,
                                       attempt.get("run_started_at"), policy.producer.workflow_path,
                                       chain["producer_blob"], chain["producer_commit"], chain["producer_ref"],
                                       attempt["event"], attempt["status"], attempt.get("conclusion"), None, {})
        P._run(source_run, policy.producer)
        candidate = chain["candidate"]
        matches = (candidate["merge_tree"] == binding["merge_tree"] and
                   candidate["merge_parents"] == binding["merge_parents"]) if integrated else (
                       chain["producer_commit"] == binding["merge_sha"])
        if not matches:
            # Fully classify a different original merge before excluding it.
            # Its source is known, but no artifacts/runtime/results are reused.
            return None, chain, []
        jobs = self._pages(f"actions/runs/{identity}/attempts/{latest_attempt}/jobs", "jobs")
        require(all(job.get("run_id") == identity and job.get("run_attempt") == latest_attempt for job in jobs),
                "latest-attempt job snapshot contains mixed executions")
        by_name = {}
        for job in jobs:
            by_name.setdefault(job.get("name"), []).append(job)
        selected = {}
        for name in [policy.publisher_job, *policy.owner_jobs.values()]:
            require(len(by_name.get(name, [])) <= 1, "selected job name is ambiguous")
            selected[name] = self._job(by_name[name][0], attempt, policy.producer.actions_app_id) if name in by_name else None
        final_jobs = [job for job in jobs if isinstance(job.get("name"), str)
                      and job["name"].startswith(policy.final_publisher_prefix)]
        require(len(final_jobs) <= 1, "final publisher commitment is ambiguous")
        publication = None
        if final_jobs:
            job = final_jobs[0]
            commitment = job["name"][len(policy.final_publisher_prefix):]
            require(re.fullmatch(r"[0-9a-f]{64}", commitment) is not None,
                    "reserved final publisher commitment is malformed")
            publication = P.AuthenticatedPublication(
                self._job(job, attempt, policy.producer.actions_app_id, final_name=job["name"]), commitment)
        run = P.AuthenticatedRun(REPOSITORY, 1319052603, suite["app"]["id"], identity, latest_attempt, latest_attempt,
                                 attempt.get("run_started_at"), policy.producer.workflow_path, chain["producer_blob"],
                                 chain["producer_commit"], chain["producer_ref"], attempt["event"], attempt["status"],
                                 attempt.get("conclusion"), selected[policy.publisher_job],
                                 {name: selected[job] for name, job in policy.owner_jobs.items() if selected[job] is not None}, publication)
        P._run(run, policy.producer)
        items = self._artifacts(run)
        raw, facts = self._artifact(run, "descriptor", items, now, binding["head_sha"])
        return P.Observation(run, raw, facts), chain, items

    def _capture_inventory(self, binding, policy, now, *, integrated=False):
        endpoint = f"actions/workflows/{policy.caller_workflow_id}/runs?head_sha={binding['head_sha']}"
        observations, chains, inventories, unavailable, other = [], {}, {}, [], {}
        try:
            listed = self._pages(endpoint, "workflow_runs", search=True)
            for item in listed:
                try:
                    observation, chain, artifacts = self._observation(item, policy, binding, now, integrated=integrated)
                    if observation is None:
                        other[positive(item.get("id"))] = chain
                        continue
                    observations.append(observation)
                    chains[observation.run.run_id] = chain
                    inventories[observation.run.run_id] = artifacts
                except OriginalAttemptUnavailable:
                    unavailable.append("original-attempt-unavailable")
                except (ApiError, P.ProtocolError, KeyError, TypeError, ValueError):
                    unavailable.append("run-source-or-proof-unclassified")
            final_list = self._pages(endpoint, "workflow_runs", search=True)
            fields = ("id", "run_attempt", "status", "conclusion", "run_started_at", "updated_at")
            require([{key: row.get(key) for key in fields} for row in listed]
                    == [{key: row.get(key) for key in fields} for row in final_list], "authority inventory changed")
        except (ApiError, KeyError, TypeError, ValueError):
            unavailable.append("run-inventory-incomplete-or-changed")
        return observations, chains, inventories, unavailable, other

    def capture(self, number, plan, policy, *, now=None):
        """Return a bookended complete API snapshot, or explicit no-reuse gaps."""
        now = now if now is not None else _now()
        P._now(now)
        _policy(policy, plan, number)
        binding, references = self.current(number)
        observations, chains, inventories, unavailable, other = self._capture_inventory(binding, policy, now)
        final_binding, final_refs = self.current(number)
        require(final_binding == binding and final_refs == references, "current PR or refs changed during API snapshot")
        return Snapshot(binding, references, observations, not unavailable, tuple(sorted(set(unavailable))), chains, inventories, other)

    def capture_integrated(self, push_run_id, plan, policy, *, now=None):
        """Look up original source facts; never alias a receipt to the push SHA."""
        now = now if now is not None else _now()
        P._now(now)
        require(isinstance(policy, AdapterPolicy), "trusted controller adapter policy required")
        P.policy_digest(policy.producer)
        integrated, references = self._integrated_current(push_run_id, policy.producer.actions_app_id, now)
        _policy(policy, plan, integrated["pull_request"])
        observations, chains, inventories, unavailable, other = self._capture_inventory(
            integrated, policy, now, integrated=True)
        originals = {item.run.workflow_commit for item in observations}
        require(len(originals) == 1, "original integrated producer candidate is missing or ambiguous")
        binding = P.validate_binding({**integrated, "merge_sha": originals.pop()})
        final_binding, final_refs = self._integrated_current(push_run_id, policy.producer.actions_app_id, now)
        require(final_binding == integrated and final_refs == references,
                "merged PR, protected push, protection or current refs changed during API snapshot")
        return Snapshot(binding, references, observations, not unavailable, tuple(sorted(set(unavailable))), chains, inventories, other)

    def verify(self, number, plan, policy, contexts, *, clock=_now):
        """Read both snapshots and validate original aggregate; no implicit rerun."""
        return self._verify(lambda now: self.capture(number, plan, policy, now=now), plan, policy, contexts, clock)

    def verify_integrated(self, push_run_id, plan, policy, contexts, *, clock=_now):
        """Verify the original evidence and separately return integration facts."""
        return self._verify(lambda now: self.capture_integrated(push_run_id, plan, policy, now=now),
                            plan, policy, contexts, clock)

    def _verify(self, capture, plan, policy, contexts, clock):
        initial = capture(clock())
        authority = P.select_authority(initial.observations, initial.binding, plan, policy.producer,
                                       inventory_complete=initial.inventory_complete, now=clock())
        require(authority["state"] == "proof-required", "newest producer is absent, pending, failed or unresolved")
        selected = next(item for item in initial.observations if item.run.run_id == authority["run_id"])
        artifacts = initial.artifact_inventories[selected.run.run_id]
        raw, artifact = self._artifact(selected.run, "aggregate", artifacts, clock(), initial.binding["head_sha"])
        require(raw is not None and artifact is not None, "newest aggregate proof is missing")
        final = capture(clock())
        require(initial.references == final.references, "current refs changed during aggregate verification")
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
        result = {**value, "source_chain": final.source_chains[value["run_id"]]}
        if "integration" in final.references:
            integration = final.references["integration"]
            merged = P._time(integration["merged_at"])
            require(P._time(value["qualified_at"]) <= merged and P._time(artifact.created_at) <= merged
                    and P._time(selected.descriptor_artifact.created_at) <= merged
                    and P._time(selected.run.final_publisher.job.completed_at) <= merged,
                    "original evidence was not complete before integration")
            result["integration"] = integration
        return result
