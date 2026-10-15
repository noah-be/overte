#!/usr/bin/env python3
"""Record provably adopted work through ordinary, checked PRs before cleanup.

Only trusted main executes. Candidate commits are inspected as Git objects in an
isolated bare repository. No candidate checkout, hooks, or merge drivers execute.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import urllib.parse
import zipfile

import cleanup

require = cleanup.require
SCOPES = {"main": "main", "android-main": "android", "android-phone": "android-phone",
          "android-vr": "android-vr", "android-vr-pico": "android-pico",
          "apple-main": "apple", "apple-ios": "ios"}
MARKER = "Branch-Cleanup-Adoption: "
PREFIX = "adopted-history-pr-"
NEGATIVE = {"merge_conflict", "tree_changes", "issue_closing_reference"}
ISSUE_CLOSE = re.compile(r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s*:?\s+"
                         r"(?:#\d+|[\w.-]+/[\w.-]+#\d+|https://github\.com/[^\s]+/issues/\d+)", re.I)


def own_pr(pr):
    return all((pr.get(side, {}).get("repo") or {}).get("id") == cleanup.REPOSITORY_ID
               and (pr.get(side, {}).get("repo") or {}).get("full_name") == cleanup.REPOSITORY
               for side in ("head", "base"))


def maintenance_branch(row):
    return f"fix/{SCOPES[row['base']]}/{PREFIX}{row['pr']}-{row['sha'][:12]}"


def fingerprint(row):
    return hashlib.sha256(json.dumps(row, sort_keys=True).encode()).hexdigest()


def discover(github, policy):
    """A closed PR is required; being stale, superseded, or unprotected is not proof."""
    plan = cleanup.make_plan(github, policy)
    branches = {row["name"]: row for row in github.branches()}
    rows, held = [], {}
    for name, reasons in sorted(plan["held"].items()):
        if reasons != ["not_fully_integrated"]:
            continue
        if name.split("/", 2)[-1].startswith(PREFIX):
            held[name] = ["maintenance_branch_requires_its_existing_pr"]
            continue
        branch = branches.get(name)
        if branch is None:
            continue
        base = cleanup.scope_target(name)
        head = urllib.parse.quote("noah-l-frank:" + name, safe="")
        prs = github.get("pulls?state=all&head=" + head + "&per_page=100", paginate=True)
        matches = [pr for pr in prs if own_pr(pr) and pr["head"]["ref"] == name
                   and pr["base"]["ref"] == base]
        if not matches:
            held[name] = ["no_completed_pull_request"]
            continue
        pr = max(matches, key=lambda item: int(item["number"]))
        if (pr.get("state") != "closed" or not pr.get("closed_at")
                or pr["head"].get("sha") != branch["sha"] or pr.get("draft")):
            held[name] = ["pull_request_does_not_complete_exact_head"]
            continue
        rows.append({"branch": name, "sha": branch["sha"], "base": base,
                     "base_sha": branches[base]["sha"], "pr": int(pr["number"])})
    # Reuse every consumer/activity hold, including keep labels on closed PRs.
    active = github.activity_holds(rows, policy)
    held.update(active)
    rows = [row for row in rows if row["branch"] not in active]
    consumers = github.workflow_holds(rows, list(branches.values()))
    held.update(consumers)
    rows = [row for row in rows if row["branch"] not in consumers]
    return rows, held, plan["source_sha"]


class Graph(cleanup.GitStore):
    def command(self, *args, check=True):
        return cleanup.run(["git", "--git-dir", str(self.path), "-c", "core.hooksPath=/dev/null",
                            "-c", "core.attributesFile=/dev/null", *args], check=check,
                           env={"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
                                "GIT_ATTR_NOSYSTEM": "1"})

    def git(self, *args):
        return self.command(*args).stdout

    def init(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            cleanup.run(["git", "-c", "init.templateDir=", "init", "--bare", str(self.path)],
                        env={"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull})
        require(not (self.path / "objects/info/alternates").exists(), "adoption_alternates_forbidden")
        self.git("config", "remote.cleanup.url", cleanup.REMOTE)
        self.git("config", "credential.helper", "!gh auth git-credential")
        # Recursive merge-base consolidation can require a synthetic Git
        # identity even though merge-tree creates no permanent commits or refs.
        self.git("config", "user.name", "Overte history assessment")
        self.git("config", "user.email", "branch-cleanup@users.noreply.github.com")

    def fetch(self, refs):
        self.verify_destination()
        require(refs and all(cleanup.valid_branch(name) and cleanup.SHA.fullmatch(sha)
                             for name, sha in refs.items()), "invalid_adoption_refs")
        self.authenticated("fetch", "--no-tags", "cleanup",
                           *[f"+refs/heads/{name}:refs/heads/{name}" for name in sorted(refs)])
        require(all(self.git("rev-parse", "refs/heads/" + name).strip() == sha
                    for name, sha in refs.items()), "adoption_ref_changed_during_fetch")

    def proof(self, row):
        if self.command("merge-base", "--is-ancestor", row["sha"], row["base_sha"], check=False).returncode == 0:
            return "already_integrated", None
        messages = self.git("log", "--format=%B", row["sha"], "--not", row["base_sha"])
        if ISSUE_CLOSE.search(messages):
            return "issue_closing_reference", None
        result = self.command("merge-tree", "--write-tree", row["base_sha"], row["sha"], check=False)
        if result.returncode == 1:
            return "merge_conflict", None
        require(result.returncode == 0, "adoption_merge_tree_failed")
        tree = result.stdout.strip()
        require(cleanup.SHA.fullmatch(tree), "invalid_adoption_tree")
        target = self.git("rev-parse", row["base_sha"] + "^{tree}").strip()
        return ("adopted", tree) if tree == target else ("tree_changes", None)

    def verify_record(self, head, row):
        """Each refresh is a fast-forward; only source and protected target histories enter."""
        seen = set()
        for _ in range(32):
            require(head not in seen, "adoption_record_cycle")
            seen.add(head)
            parents = self.git("show", "-s", "--format=%P", head).split()
            message = self.git("show", "-s", "--format=%B", head)
            records = [line[len(MARKER):] for line in message.splitlines() if line.startswith(MARKER)]
            require(len(records) == 1 and len(parents) == 2, "invalid_adoption_record")
            record = json.loads(records[0])
            expected = {key: row[key] for key in ("branch", "sha", "base", "pr")}
            require(record == dict(expected, base_sha=parents[0]), "adoption_record_binding_mismatch")
            require(self.command("merge-base", "--is-ancestor", parents[0], row["base_sha"],
                                 check=False).returncode == 0, "adoption_target_history_changed")
            require(self.git("rev-parse", head + "^{tree}").strip()
                    == self.git("rev-parse", parents[0] + "^{tree}").strip(), "adoption_record_changes_files")
            if parents[1] == row["sha"]:
                return
            head = parents[1]
        raise cleanup.CleanupError("adoption_refresh_limit_reached")


def load_negative_cache(github, version):
    """A cached negative result can only defer work; positive proofs are never cached."""
    runs = github.get("actions/workflows/branch-cleanup.yml/runs?status=success&per_page=5")
    for run in runs.get("workflow_runs", []):
        if run["id"] == int(os.environ.get("GITHUB_RUN_ID", "0")):
            continue
        artifacts = github.get(f"actions/runs/{int(run['id'])}/artifacts?per_page=100")
        expected = f"branch-cleanup-report-{run['id']}-{run['run_attempt']}"
        for artifact in artifacts.get("artifacts", []):
            if artifact.get("name") != expected or artifact.get("expired"):
                continue
            require(0 < artifact.get("size_in_bytes", 0) <= 2_000_000, "adoption_cache_too_large")
            # Never extract paths or execute artifact contents. The only accepted
            # values are negative verdicts for exact source/target/version tuples.
            result = subprocess.run(["gh", "api", "--method", "GET", "repos/" + cleanup.REPOSITORY
                                     + f"/actions/artifacts/{int(artifact['id'])}/zip"],
                                    capture_output=True, timeout=180)
            require(result.returncode == 0 and len(result.stdout) <= 2_000_000, "adoption_cache_unavailable")
            with zipfile.ZipFile(io.BytesIO(result.stdout)) as archive:
                if "adoption.json" not in archive.namelist():
                    continue
                require(archive.getinfo("adoption.json").file_size <= 1_000_000, "adoption_cache_too_large")
                value = json.loads(archive.read("adoption.json"))
            require(isinstance(value, dict) and isinstance(value.get("negative", {}), dict),
                    "invalid_adoption_cache")
            if value.get("version") == version and value.get("repository") == cleanup.REPOSITORY:
                return {key: verdict for key, verdict in value.get("negative", {}).items()
                        if re.fullmatch(r"[0-9a-f]{64}", key) and verdict in NEGATIVE}
    return {}


class Writer:
    def __init__(self, github, root, token, slug):
        self.github, self.root, self.token, self.slug = github, root, token, slug

    def write(self, suffix, method, value):
        cleanup.trusted_runtime()
        self.github.verify_owner()
        main = self.github.get("git/ref/heads/main")["object"]["sha"]
        cleanup.verify_checkout(self.root, main)
        require(self.token and re.fullmatch(r"[a-z0-9-]+", self.slug), "adoption_app_not_configured")
        require(not suffix.startswith(("/", "http")) and ".." not in suffix.split("/"), "unsafe_adoption_write")
        result = cleanup.run(["gh", "api", "--method", method, "repos/" + cleanup.REPOSITORY
                              + "/" + suffix, "--input", "-"], input=json.dumps(value),
                             env={"GH_TOKEN": self.token})
        return json.loads(result.stdout)

    def guard(self, row, policy):
        self.github.verify_owner()
        branches = self.github.branches()
        indexed = {item["name"]: item for item in branches}
        require(indexed.get(row["branch"], {}).get("sha") == row["sha"]
                and indexed.get(row["base"], {}).get("sha") == row["base_sha"]
                and indexed[row["base"]]["protected"]
                and not indexed[row["branch"]]["protected"], "adoption_heads_changed")
        require(row["branch"] not in policy["holds"], "adoption_explicit_hold")
        pr = self.github.get("pulls/" + str(row["pr"]))
        require(own_pr(pr) and pr.get("state") == "closed" and pr.get("closed_at")
                and pr["head"]["ref"] == row["branch"] and pr["head"]["sha"] == row["sha"]
                and pr["base"]["ref"] == row["base"], "adoption_completion_changed")
        require(not self.github.activity_holds([row], policy)
                and not self.github.workflow_holds([row], branches), "adoption_consumer_or_activity_hold")
        rules = self.github.get("rules/branches/" + urllib.parse.quote(row["base"], safe=""))
        require({"deletion", "non_fast_forward", "pull_request", "required_status_checks"}
                <= {rule["type"] for rule in rules}, "adoption_target_checks_not_protected")
        checks = [rule for rule in rules if rule["type"] == "required_status_checks"]
        require(all(rule["parameters"].get("strict_required_status_checks_policy") is True
                    and rule["parameters"].get("required_status_checks") for rule in checks),
                "adoption_target_checks_not_strict")
        configuration = json.loads((self.root / ".github/repository-checks.json").read_text())
        require(configuration.get("repository") == cleanup.REPOSITORY
                and configuration.get("repository_id") == cleanup.REPOSITORY_ID,
                "adoption_required_checks_policy_mismatch")
        expected = set(configuration["required_contexts"])
        actual = {item["context"] for rule in checks for item in rule["parameters"]["required_status_checks"]
                  if item.get("integration_id") == 15368}
        require(expected and expected <= actual, "adoption_required_check_missing")
        for ruleset in {rule["ruleset_id"] for rule in rules}:
            metadata = self.github.get("rulesets/" + str(int(ruleset)))
            # GitHub omits this administrator-only field from installation-token
            # responses. Readiness below independently requires every check and
            # the PR's review/merge decision; no extra App privilege is needed.
            if "bypass_actors" in metadata:
                require(metadata["bypass_actors"] == [], "adoption_ruleset_has_bypass_actors")
        return [item for rule in checks for item in rule["parameters"]["required_status_checks"]]

    def ready(self, pr, row, required):
        """Read checks independently of the writing App's permissions or bypass list."""
        head = pr["head"]["sha"]
        page = self.github.get(f"commits/{head}/check-runs?filter=latest&per_page=100")
        runs = page.get("check_runs")
        require(isinstance(runs, list) and page.get("total_count") == len(runs),
                "adoption_check_listing_incomplete")
        for check in required:
            matches = [run for run in runs if run.get("name") == check["context"]
                       and (check.get("integration_id") is None
                            or run.get("app", {}).get("id") == check["integration_id"])]
            if not matches:
                return False
            latest = max(matches, key=lambda run: int(run["id"]))
            if (latest.get("head_sha") != head or latest.get("status") != "completed"
                    or latest.get("conclusion") != "success"):
                return False
        query = ('query($number:Int!){repository(owner:"noah-l-frank",name:"overte"){nameWithOwner '
                 'pullRequest(number:$number){headRefOid baseRefOid baseRefName mergeStateStatus reviewDecision '
                 'closingIssuesReferences(first:1){totalCount}}}}')
        result = json.loads(cleanup.run(["gh", "api", "graphql", "-f", "query=" + query,
                                        "-F", "number=" + str(int(pr["number"]))]).stdout)
        repository = result["data"]["repository"]
        state = repository["pullRequest"]
        require(repository["nameWithOwner"] == cleanup.REPOSITORY and state["headRefOid"] == head
                and state["baseRefName"] == row["base"] and state["baseRefOid"] == row["base_sha"],
                "adoption_check_identity_changed")
        return (state["mergeStateStatus"] == "CLEAN" and state["reviewDecision"] in (None, "APPROVED")
                and state["closingIssuesReferences"]["totalCount"] == 0)

    def record(self, row, tree, previous=None):
        message = f"Record adopted history from PR #{row['pr']}\n\n" + MARKER + json.dumps(row, sort_keys=True)
        value = self.write("git/commits", "POST", {
            "message": message, "tree": tree, "parents": [row["base_sha"], previous or row["sha"]]})
        require(cleanup.SHA.fullmatch(value.get("sha", "")), "adoption_commit_readback_mismatch")
        value = self.github.get("git/commits/" + value["sha"])
        require(cleanup.SHA.fullmatch(value.get("sha", "")) and value.get("tree", {}).get("sha") == tree
                and [item["sha"] for item in value.get("parents", [])]
                == [row["base_sha"], previous or row["sha"]], "adoption_commit_readback_mismatch")
        return value["sha"]

    def reconcile(self, row, tree, graph, policy):
        branch = maintenance_branch(row)
        head = urllib.parse.quote("noah-l-frank:" + branch, safe="")
        prs = self.github.get("pulls?state=all&head=" + head + "&per_page=100", paginate=True)
        require(all(own_pr(pr) and pr["head"]["ref"] == branch and pr["base"]["ref"] == row["base"]
                    for pr in prs), "adoption_pr_ownership_mismatch")
        if prs:
            pr = max(prs, key=lambda item: int(item["number"]))
            require(pr.get("user", {}).get("login") == self.slug + "[bot]", "adoption_pr_author_mismatch")
            if pr["state"] != "open":
                return "previous_adoption_pr_closed", False, False
            if pr.get("draft") or policy["keep_label"] in {label["name"] for label in pr.get("labels", [])}:
                return "adoption_pr_held", False, False
            current = pr["head"]["sha"]
        else:
            current = next((item["sha"] for item in self.github.branches() if item["name"] == branch), None)
        if current:
            graph.fetch({branch: current})
            graph.verify_record(current, row)
        self.guard(row, policy)
        if current is None:
            cleanup.run(["python3", str(self.root / "tools/branch-policy/check.py"),
                         "check-name", "--branch", branch])
            current = self.record(row, tree)
            ref = self.write("git/refs", "POST", {"ref": "refs/heads/" + branch, "sha": current})
            require(ref.get("ref") == "refs/heads/" + branch and ref.get("object", {}).get("sha") == current,
                    "adoption_ref_readback_mismatch")
            saved_ref = self.github.get("git/ref/heads/" + urllib.parse.quote(branch, safe=""))
            require(saved_ref.get("object", {}).get("sha") == current, "adoption_ref_readback_mismatch")
        elif graph.git("show", "-s", "--format=%P", current).split()[0] != row["base_sha"]:
            updated = self.record(row, tree, current)
            ref = self.write("git/refs/heads/" + urllib.parse.quote(branch, safe=""), "PATCH",
                             {"sha": updated, "force": False})
            require(ref.get("object", {}).get("sha") == updated, "adoption_ref_readback_mismatch")
            saved_ref = self.github.get("git/ref/heads/" + urllib.parse.quote(branch, safe=""))
            require(saved_ref.get("object", {}).get("sha") == updated, "adoption_ref_readback_mismatch")
            return "refreshed_waiting_for_checks", False, True
        if not prs:
            body = (f"The exact head of closed PR #{row['pr']} is already represented in `{row['base']}`.\n\n"
                    f"Source: `{row['branch']}` at `{row['sha']}`. Target: `{row['base_sha']}`.\n\n"
                    f"A normal, conflict-free Git merge produces the identical target tree `{tree}`. "
                    "This PR records the original history without changing any files. All normal required "
                    "checks and branch protections must pass. Branch deletion remains a separate, backed-up "
                    "cleanup operation after integration. No issues are closed.\n\n"
                    "Material AI assistance: Codex authored the trusted cleanup automation; Git computed this proof.")
            created = self.write("pulls", "POST", {"head": branch, "base": row["base"],
                                 "title": f"Record adopted history from PR #{row['pr']}", "body": body})
            saved = self.github.get("pulls/" + str(int(created["number"])))
            require(own_pr(saved) and saved["head"]["sha"] == current
                    and saved["head"]["ref"] == branch and saved["base"]["ref"] == row["base"]
                    and saved.get("user", {}).get("login") == self.slug + "[bot]",
                    "adoption_pr_readback_mismatch")
            self.write(f"issues/{saved['number']}/labels", "POST", {"labels": ["type: task"]})
            labels = self.github.get(f"issues/{saved['number']}/labels")
            require("type: task" in {label["name"] for label in labels}, "adoption_pr_label_not_saved")
            return "created_waiting_for_checks", False, True
        pr = self.github.get("pulls/" + str(int(pr["number"])))
        require(own_pr(pr) and pr["head"]["sha"] == current and pr["state"] == "open"
                and pr["head"]["ref"] == branch and pr["base"]["ref"] == row["base"]
                and not pr.get("draft") and pr.get("user", {}).get("login") == self.slug + "[bot]"
                and policy["keep_label"] not in {label["name"] for label in pr.get("labels", [])},
                "adoption_pr_changed")
        if pr.get("mergeable_state") != "clean" or pr.get("mergeable") is not True:
            return "waiting_for_required_checks", False, False
        # A final fresh merge proof and hold check precede the normal PR merge API.
        require(graph.proof(row) == ("adopted", tree), "adoption_proof_changed")
        required = self.guard(row, policy)
        if not self.ready(pr, row, required):
            return "waiting_for_required_checks", False, False
        result = self.write(f"pulls/{pr['number']}/merge", "PUT", {"sha": current, "merge_method": "merge"})
        require(result.get("merged") is True, "adoption_pr_merge_not_accepted")
        saved = self.github.get("pulls/" + str(int(pr["number"])))
        require(own_pr(saved) and saved.get("merged") is True, "adoption_merge_readback_mismatch")
        commit = self.github.get("git/commits/" + saved["merge_commit_sha"])
        require(commit.get("tree", {}).get("sha") == tree
                and [item["sha"] for item in commit.get("parents", [])] == [row["base_sha"], current],
                "adoption_merge_tree_readback_mismatch")
        return "integrated", row["base"] == "main", True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    policy = cleanup.validate_policy(json.loads((root / ".github/branch-cleanup.json").read_text()))
    version = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    report = {"repository": cleanup.REPOSITORY, "version": version, "status": "started",
              "results": {}, "held": {}, "negative": {}, "main_advanced": False}
    try:
        github = cleanup.Github()
        rows, report["held"], source_sha = discover(github, policy)
        if os.environ.get("GITHUB_ACTIONS") == "true":
            cleanup.verify_checkout(root, source_sha)
        token, slug = os.environ.get("ADOPTION_APP_TOKEN", ""), os.environ.get("ADOPTION_APP_SLUG", "")
        write = args.apply and bool(token and slug)
        writer = Writer(github, root, token, slug)
        cached = load_negative_cache(github, version)
        report["negative"] = dict(cached)
        wrote = False
        with tempfile.TemporaryDirectory(prefix="branch-adoption-") as directory:
            graph = Graph(Path(directory) / "graph.git")
            for row in rows:
                key = fingerprint(row)
                if key in cached:
                    verdict, tree = cached[key], None
                else:
                    graph.fetch({row["branch"]: row["sha"], row["base"]: row["base_sha"]})
                    verdict, tree = graph.proof(row)
                if verdict in NEGATIVE:
                    report["negative"][key] = verdict
                elif verdict == "adopted" and write and not wrote:
                    try:
                        verdict, report["main_advanced"], wrote = writer.reconcile(row, tree, graph, policy)
                    except cleanup.CleanupError as error:
                        if str(error) not in {"adoption_heads_changed", "adoption_completion_changed",
                                              "adoption_consumer_or_activity_hold", "adoption_explicit_hold",
                                              "adoption_pr_changed"}:
                            raise
                        verdict = str(error)
                report["results"][row["branch"]] = verdict
                if report["main_advanced"]:
                    break
        report["negative"] = dict(list(report["negative"].items())[-128:])
        report["status"] = "assessed" if not args.apply or write else "app_not_configured_report_only"
    except (cleanup.CleanupError, OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile,
            subprocess.TimeoutExpired) as error:
        report.update(status="blocked", error=str(error) if isinstance(error, cleanup.CleanupError)
                      else type(error).__name__)
        cleanup.write_json(args.report, report)
        print("Adoption assessment stopped; inspect its redacted report.")
        return 1
    cleanup.write_json(args.report, report)
    if os.environ.get("GITHUB_OUTPUT"):
        with Path(os.environ["GITHUB_OUTPUT"]).open("a") as out:
            out.write("main_advanced=" + str(report["main_advanced"]).lower() + "\n")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a") as out:
            out.write("### Adopted branch history\n\nStatus: **" + report["status"] + "**.\n\n")
            for branch, verdict in report["results"].items():
                out.write("- `" + branch.replace("`", "") + "`: " + verdict + "\n")
    print(json.dumps({"status": report["status"], "assessed": len(report["results"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
