#!/usr/bin/env python3
"""GitHub-hosted, fail-closed cleanup of integrated branches in one exact fork.

Candidate source is never checked out or executed. No local device or workstation
is contacted. Persistent exceptions and PR labels are the work-ownership signal.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import urllib.parse

REPOSITORY = "noah-be/overte"
REPOSITORY_ID = 1319052603
REMOTE = "https://github.com/noah-be/overte.git"
WORKFLOW = ".github/workflows/branch-cleanup.yml"
ARCHIVE_PREFIX = "archive/merged/"
PERMANENT = {
    "main", "android-main", "android-phone", "android-vr", "android-vr-pico",
    "apple-main", "apple-ios", "linux-main", "windows-main",
}
SCOPES = {
    "main": "main", "android": "android-main", "android-main": "android-main",
    "android-phone": "android-phone", "android-vr": "android-vr",
    "android-pico": "android-vr-pico", "android-vr-pico": "android-vr-pico",
    "apple": "apple-main", "ios": "apple-ios", "linux": "linux-main",
    "windows": "windows-main",
}
KINDS = {"feature", "fix", "docs", "refactor", "test", "tests", "task", "ci", "sync", "reconcile", "promote", "build"}
SHA = re.compile(r"^[0-9a-f]{40}$")


class CleanupError(RuntimeError):
    """An incomplete or unsafe condition; no fallback authorization is implied."""


def require(condition, reason):
    if not condition:
        raise CleanupError(reason)


def run(args, **kwargs):
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_OPTIONAL_LOCKS="0")
    env.update(kwargs.pop("env", {}))
    check = kwargs.pop("check", True)
    result = subprocess.run(args, capture_output=True, text=True, env=env,
                            timeout=kwargs.pop("timeout", 1200), **kwargs)
    if check and result.returncode:
        # Do not relay arbitrary command output, credentials, or API payloads.
        raise CleanupError(f"{Path(args[0]).name}_failed_exit_{result.returncode}")
    return result


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def valid_branch(name):
    return isinstance(name, str) and run(["git", "check-ref-format", "refs/heads/" + name], check=False).returncode == 0


def validate_policy(value):
    require(isinstance(value, dict) and value.get("schema") == 1, "invalid_policy_schema")
    require(value.get("repository") == REPOSITORY and value.get("repository_id") == REPOSITORY_ID, "foreign_repository_policy")
    names = value.get("permanent_branches", [])
    require(isinstance(names, list) and len(names) == len(PERMANENT) and set(names) == PERMANENT, "permanent_branch_policy_changed")
    require(value.get("archive_tag_prefix") == ARCHIVE_PREFIX, "unsafe_archive_prefix")
    require(value.get("artifact_retention_days") == 30, "unexpected_backup_retention")
    require(value.get("keep_label") == "keep-branch", "unexpected_keep_label")
    holds = value.get("holds")
    require(isinstance(holds, dict), "invalid_holds")
    require(all(valid_branch(name) and isinstance(reason, str) and reason.strip() for name, reason in holds.items()), "invalid_hold_entry")
    return value


def scope_target(branch):
    parts = branch.split("/", 2)
    if len(parts) != 3 or parts[0] not in KINDS or not parts[2]:
        return None
    return SCOPES.get(parts[1])


def select_candidates(branches, policy, comparisons, holds=None):
    validate_policy(policy)
    require(isinstance(branches, list) and all(
        isinstance(row, dict) and valid_branch(row.get("name"))
        and isinstance(row.get("sha"), str) and SHA.fullmatch(row["sha"])
        and isinstance(row.get("protected"), bool) for row in branches), "invalid_remote_branch_metadata")
    indexed = {row["name"]: row for row in branches}
    require(len(indexed) == len(branches), "duplicate_remote_branch")
    require(PERMANENT <= indexed.keys(), "permanent_branch_missing")
    require(all(indexed[name].get("protected") is True for name in PERMANENT), "permanent_branch_unprotected")
    result, held = [], {}
    for name, row in sorted(indexed.items()):
        reasons = list((holds or {}).get(name, []))
        if name in PERMANENT or row.get("protected"):
            reasons.append("permanent_or_protected")
        if name in policy["holds"]:
            reasons.append("explicit_work_hold")
        target = scope_target(name)
        if target is None and name not in PERMANENT:
            reasons.append("unmanaged_branch_scope")
        require(valid_branch(name) and SHA.fullmatch(row["sha"]), "invalid_remote_branch")
        if not reasons:
            comparison = comparisons.get(name)
            if not (isinstance(comparison, dict)
                    and comparison.get("status") in {"ahead", "identical"}
                    and comparison.get("behind_by") == 0
                    and comparison.get("merge_base_commit", {}).get("sha") == row["sha"]):
                reasons.append("not_fully_integrated")
        if reasons:
            held[name] = sorted(set(reasons))
        else:
            result.append({"branch": name, "sha": row["sha"], "base": target,
                           "base_sha": indexed[target]["sha"]})
    return result, held


class Github:
    def get(self, suffix="", paginate=False):
        require(not suffix.startswith(("/", "http"))
                and not {".", ".."}.intersection(suffix.split("?", 1)[0].split("/")), "unsafe_api_path")
        endpoint = "repos/" + REPOSITORY + ("/" + suffix if suffix else "")
        args = ["gh", "api", "--method", "GET", endpoint]
        if paginate:
            args += ["--paginate", "--slurp"]
        value = json.loads(run(args, timeout=180).stdout)
        if not paginate:
            return value
        require(isinstance(value, list), "invalid_api_pages")
        if all(isinstance(page, list) for page in value):
            return [item for page in value for item in page]
        require(len(value) == 1, "unexpected_object_pagination")
        return value[0]

    def verify_owner(self):
        value = self.get()
        require(value.get("full_name") == REPOSITORY and value.get("id") == REPOSITORY_ID,
                "repository_ownership_mismatch")
        require(value.get("default_branch") == "main", "default_branch_changed")
        require(value.get("delete_branch_on_merge") is False, "native_cleanup_would_bypass_guards")
        return value

    def verify_archive_protection(self):
        rulesets = self.get("rulesets?includes_parents=true&per_page=100", paginate=True)
        for summary in rulesets:
            if summary.get("target") != "tag" or summary.get("enforcement") != "active":
                continue
            ruleset = self.get("rulesets/" + str(int(summary["id"])))
            if ruleset.get("target") != "tag" or ruleset.get("enforcement") != "active":
                continue
            conditions = ruleset.get("conditions", {}).get("ref_name", {})
            # Require the reviewed broad archive rule, not a coincidental tag match.
            if "refs/tags/archive/**" not in conditions.get("include", []):
                continue
            if conditions.get("exclude"):
                continue
            types = {rule.get("type") for rule in ruleset.get("rules", [])}
            if {"deletion", "non_fast_forward"} <= types:
                # Non-admin API callers cannot see bypass_actors. Do not invent an
                # empty list: protection here means the active restriction rules.
                return
        raise CleanupError("archive_tag_protection_missing")

    def branches(self):
        rows = self.get("branches?per_page=100", paginate=True)
        return [{"name": r["name"], "sha": r["commit"]["sha"], "protected": r["protected"]} for r in rows]

    def open_pr_holds(self, names):
        held = {}
        for pr in self.get("pulls?state=open&per_page=100", paginate=True):
            for side in ["head", "base"]:
                ref = pr[side]
                if ref.get("repo", {}) and ref["repo"].get("id") == REPOSITORY_ID and ref["ref"] in names:
                    held.setdefault(ref["ref"], []).append("open_pull_request_" + side)
        return held

    def activity_holds(self, candidates, policy):
        names = {r["branch"] for r in candidates}
        held = self.open_pr_holds(names)
        if not names:
            return held
        own_run = int(os.environ.get("GITHUB_RUN_ID", "0"))
        endpoints = ["actions/runs?status=" + status + "&per_page=100" for status in
                     ["queued", "in_progress", "waiting", "pending", "requested"]]
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
            pages = list(pool.map(lambda endpoint: self.get(endpoint, paginate=True), endpoints))
        active = []
        for page in pages:
            require(isinstance(page, dict) and isinstance(page.get("total_count"), int)
                    and isinstance(page.get("workflow_runs"), list), "active_run_listing_invalid")
            require(page.get("total_count", 0) == len(page.get("workflow_runs", [])), "active_run_listing_incomplete")
            active += [r for r in page["workflow_runs"] if r["id"] != own_run
                       and r.get("path", "").split("@", 1)[0] != WORKFLOW]
        for row in candidates:
            refs = {row["branch"], row.get("base")}
            commits = {row["sha"], row.get("base_sha")}
            refs.discard(None)
            commits.discard(None)
            for workflow_run in active:
                branch, sha = workflow_run.get("head_branch"), workflow_run.get("head_sha")
                require(isinstance(branch, str) and branch and isinstance(sha, str)
                        and SHA.fullmatch(sha), "active_run_reference_unknown")
                related = branch in refs or sha in commits
                for pr in workflow_run.get("pull_requests", []):
                    related |= any(pr.get(side, {}).get("ref") in refs
                                   or pr.get(side, {}).get("sha") in commits for side in ["head", "base"])
                if related:
                    held.setdefault(row["branch"], []).append("github_actions_still_active")
                    break
        for row in candidates:
            head = urllib.parse.quote("noah-be:" + row["branch"], safe="")
            prs = self.get("pulls?state=all&head=" + head + "&per_page=100", paginate=True)
            if any(policy["keep_label"] in {label["name"] for label in pr.get("labels", [])} for pr in prs):
                held.setdefault(row["branch"], []).append("keep_branch_label")
        for endpoint, field, reason in [("deployments?per_page=100", "ref", "deployment_reference"),
                                         ("releases?per_page=100", "target_commitish", "release_reference")]:
            for entry in self.get(endpoint, paginate=True):
                value = entry.get(field, "")
                for row in candidates:
                    if value in {row["branch"], "refs/heads/" + row["branch"], row["sha"]}:
                        held.setdefault(row["branch"], []).append(reason)
        # Open task descriptions are part of the repository's ownership record.
        # Comments are inspected only for explicitly active tasks; a keep-branch
        # label or policy hold is the durable way to reserve work outside GitHub.
        for issue in self.get("issues?state=open&per_page=100", paginate=True):
            if "pull_request" in issue:
                continue
            texts = [issue.get("body") or ""]
            labels = {label["name"] for label in issue.get("labels", [])}
            if "workflow: active" in labels and issue.get("comments", 0):
                comments = self.get("issues/" + str(int(issue["number"])) + "/comments?per_page=100", paginate=True)
                texts += [comment.get("body") or "" for comment in comments]
            for row in candidates:
                if any(row["branch"] in text or urllib.parse.quote(row["branch"], safe="") in text for text in texts):
                    held.setdefault(row["branch"], []).append("open_issue_reference")
        return held

    def workflow_holds(self, candidates, branches):
        """Read workflow references at permanent commit SHAs without a checkout."""
        if not candidates:
            return {}
        import base64
        import binascii

        require(isinstance(candidates, list) and all(
            isinstance(row, dict) and isinstance(row.get("branch"), str)
            and row["branch"] for row in candidates), "invalid_workflow_candidates")
        names = {row["branch"] for row in candidates}
        require(len(names) == len(candidates), "duplicate_workflow_candidate")
        require(isinstance(branches, list) and all(
            isinstance(row, dict) and isinstance(row.get("name"), str) for row in branches),
                "invalid_workflow_branch_metadata")
        indexed = {row.get("name"): row.get("sha") for row in branches}
        require(len(indexed) == len(branches), "duplicate_workflow_branch_metadata")
        require(PERMANENT <= indexed.keys() and all(
            isinstance(indexed[name], str) and SHA.fullmatch(indexed[name])
            for name in PERMANENT), "invalid_permanent_workflow_revision")
        patterns = {name: re.compile(r"(?<![A-Za-z0-9_.-])" + re.escape(name)
                                     + r"(?![A-Za-z0-9_.-])") for name in names}

        def directory(name):
            revision = indexed[name]
            entries = self.get("contents/.github/workflows?ref=" + revision)
            require(isinstance(entries, list) and len(entries) < 1000,
                    "workflow_directory_listing_incomplete")
            files, seen = [], set()
            for entry in entries:
                require(isinstance(entry, dict) and isinstance(entry.get("path"), str),
                        "invalid_workflow_directory_entry")
                path = entry["path"]
                require(path.startswith(".github/workflows/")
                        and "/" not in path.removeprefix(".github/workflows/")
                        and path.removeprefix(".github/workflows/") not in {"", ".", ".."}
                        and not any(char in path for char in "\r\n\0")
                        and path not in seen, "invalid_workflow_directory_path")
                seen.add(path)
                if not path.endswith((".yml", ".yaml")):
                    continue
                require(entry.get("type") == "file" and isinstance(entry.get("sha"), str)
                        and SHA.fullmatch(entry["sha"]), "invalid_workflow_file_entry")
                files.append((name, revision, path, entry["sha"]))
            return files

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            directories = list(pool.map(directory, sorted(PERMANENT)))
        # Identical files shared by permanent branches need only one content GET.
        # The decoded Git blob hash below verifies that reuse is exact.
        objects = {}
        for files in directories:
            for name, revision, path, blob_sha in files:
                objects.setdefault((path, blob_sha), []).append((name, revision))

        def references(item):
            (path, blob_sha), owners = item
            revision = owners[0][1]
            value = self.get("contents/" + urllib.parse.quote(path, safe="/")
                             + "?ref=" + revision)
            require(isinstance(value, dict) and value.get("type") == "file"
                    and value.get("path") == path and value.get("sha") == blob_sha
                    and value.get("encoding") == "base64"
                    and isinstance(value.get("content"), str)
                    and "target" not in value and "submodule_git_url" not in value,
                    "invalid_workflow_file_response")
            require(len(value["content"]) <= 2_000_000, "workflow_content_too_large")
            try:
                encoded = value["content"].encode("ascii")
                raw = base64.b64decode(re.sub(rb"[ \t\r\n]", b"", encoded), validate=True)
                source = raw.decode("utf-8")
            except (UnicodeError, ValueError, binascii.Error):
                raise CleanupError("invalid_workflow_content_encoding") from None
            actual = hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()
            require(actual == blob_sha, "workflow_blob_identity_mismatch")
            if "size" in value:
                require(type(value["size"]) is int and value["size"] == len(raw),
                        "workflow_content_size_mismatch")
            texts = (source, urllib.parse.unquote(source))
            matches = {name for name, pattern in patterns.items()
                       if any(pattern.search(text) for text in texts)}
            return path, owners, matches

        held = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            for path, owners, matches in pool.map(references, sorted(objects.items())):
                for name in matches:
                    held.setdefault(name, []).extend(
                        "permanent_workflow_reference:" + owner + ":" + path
                        for owner, _ in owners)
        return {name: sorted(set(reasons)) for name, reasons in sorted(held.items())}

    def comparisons(self, branches, policy, held):
        indexed = {r["name"]: r for r in branches}
        pending = []
        for row in branches:
            name = row["name"]
            target = scope_target(name)
            if target and not row["protected"] and name not in policy["holds"] and name not in held:
                pending.append((name, row["sha"], indexed[target]["sha"]))
        def compare(item):
            name, head, base = item
            return name, self.get("compare/" + head + "..." + base + "?per_page=1")
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            return dict(pool.map(compare, pending))


def make_plan(github, policy):
    github.verify_owner()
    branches = github.branches()
    indexed = {r["name"]: r for r in branches}
    require(PERMANENT <= indexed.keys(), "permanent_branch_missing")
    held = github.open_pr_holds(set(indexed))
    comparisons = github.comparisons(branches, policy, held)
    candidates, held = select_candidates(branches, policy, comparisons, held)
    activities = github.activity_holds(candidates, policy)
    for name, reasons in activities.items():
        held.setdefault(name, []).extend(reasons)
    candidates = [r for r in candidates if r["branch"] not in activities]
    consumers = github.workflow_holds(candidates, branches)
    for name, reasons in consumers.items():
        held.setdefault(name, []).extend(reasons)
    candidates = [r for r in candidates if r["branch"] not in consumers]
    for base in {r["base"] for r in candidates}:
        rules = github.get("rules/branches/" + urllib.parse.quote(base, safe=""))
        require({"deletion", "non_fast_forward"} <= {r["type"] for r in rules}, "target_history_not_protected")
    if candidates:
        github.verify_archive_protection()
    return {"schema": 1, "repository": REPOSITORY, "repository_id": REPOSITORY_ID,
            "source_sha": indexed["main"]["sha"], "policy_sha256": hashlib.sha256(json.dumps(policy, sort_keys=True).encode()).hexdigest(),
            "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "candidates": candidates, "held": held, "candidate_count": len(candidates)}


class GitStore:
    def __init__(self, path):
        self.path = Path(path)

    def git(self, *args):
        return run(["git", "--git-dir", str(self.path), *args]).stdout

    def init(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            run(["git", "init", "--bare", str(self.path)])
        require(not (self.path / "objects/info/alternates").exists(), "git_alternates_forbidden")
        self.git("config", "remote.cleanup.url", REMOTE)

    def verify_destination(self):
        self.init()
        require(self.git("remote", "get-url", "--push", "--all", "cleanup").splitlines() == [REMOTE], "push_destination_mismatch")

    def authenticated(self, *args):
        return self.git("-c", "credential.helper=", "-c", "credential.helper=!gh auth git-credential", *args)

    def fetch(self, candidates):
        self.verify_destination()
        for row in candidates:
            require(valid_branch(row["branch"]) and SHA.fullmatch(row["sha"]), "invalid_candidate")
        self.authenticated("fetch", "--no-tags", "cleanup",
                           *["+refs/heads/" + r["branch"] + ":refs/heads/" + r["branch"] for r in candidates])
        for row in candidates:
            require(self.git("rev-parse", "refs/heads/" + row["branch"]).strip() == row["sha"], "candidate_changed_during_fetch")

    def remote_archive(self, sha):
        tag = "refs/tags/" + ARCHIVE_PREFIX + sha
        output = self.authenticated("ls-remote", "--tags", "cleanup", tag, tag + "^{}")
        return {ref: oid for oid, ref in (line.split() for line in output.splitlines())}

    def verify_archives(self, candidates):
        for row in candidates:
            name = "refs/tags/" + ARCHIVE_PREFIX + row["sha"]
            remote = self.remote_archive(row["sha"])
            require(name in remote and remote.get(name + "^{}") == row["sha"], "annotated_recovery_tag_missing_or_mismatched")

    def backup_tags(self, candidates, github):
        github.verify_archive_protection()
        refs = []
        seen = set()
        for row in candidates:
            sha = row["sha"]
            if sha in seen:
                continue
            seen.add(sha)
            name = ARCHIVE_PREFIX + sha
            remote = self.remote_archive(sha)
            if remote:
                require(remote.get("refs/tags/" + name + "^{}") == sha, "recovery_tag_collision")
                continue
            self.git("-c", "user.name=Overte branch cleanup", "-c", "user.email=branch-cleanup@users.noreply.github.com",
                     "tag", "-a", name, sha, "-m", "Verified integrated branch recovery\nRepository: " + REPOSITORY + "\nOriginal branch: " + row["branch"] + "\nCommit: " + sha)
            refs.append("refs/tags/" + name + ":refs/tags/" + name)
        if refs:
            self.verify_destination()
            github.verify_owner()
            self.authenticated("push", "--atomic", "cleanup", *sorted(set(refs)))
        self.verify_archives(candidates)

    def delete(self, candidates, github):
        if not candidates:
            return []
        require(all(valid_branch(r.get("branch")) and isinstance(r.get("sha"), str)
                    and SHA.fullmatch(r["sha"]) for r in candidates), "invalid_delete_candidate")
        require(len({r["branch"] for r in candidates}) == len(candidates), "duplicate_delete_candidate")
        require(all(r["branch"] not in PERMANENT and scope_target(r["branch"]) for r in candidates), "protected_or_unmanaged_delete")
        self.verify_archives(candidates)
        self.verify_destination()
        github.verify_owner()
        output = self.authenticated("push", "--porcelain", "--atomic",
                                    *["--force-with-lease=refs/heads/" + r["branch"] + ":" + r["sha"] for r in candidates],
                                    "cleanup", *[":refs/heads/" + r["branch"] for r in candidates])
        require(len([line for line in output.splitlines() if line.startswith("-\t")]) == len(candidates), "unexpected_delete_response")
        remaining = self.authenticated("ls-remote", "--heads", "cleanup", *["refs/heads/" + r["branch"] for r in candidates])
        require(not remaining.strip(), "deleted_branch_still_present")
        return [r["branch"] for r in candidates]


def create_bundle(repo_dir, candidates, output):
    store = GitStore(repo_dir)
    require(candidates, "empty_backup")
    for row in candidates:
        require(store.git("rev-parse", "refs/heads/" + row["branch"]).strip() == row["sha"], "backup_head_mismatch")
    store.git("bundle", "create", str(output), *["refs/heads/" + row["branch"] for row in candidates])
    return digest(output)


def verify_bundle(bundle, candidates, restore_dir):
    bundle, restore_dir = Path(bundle).resolve(), Path(restore_dir)
    require(not restore_dir.exists(), "restore_repository_must_be_new")
    run(["git", "init", "--bare", str(restore_dir)])
    store = GitStore(restore_dir)
    store.git("bundle", "verify", str(bundle))
    listed = store.git("bundle", "list-heads", str(bundle))
    actual = {ref: sha for sha, ref in (line.split() for line in listed.splitlines())}
    expected = {"refs/heads/" + row["branch"]: row["sha"] for row in candidates}
    require(actual == expected, "backup_refs_mismatch")
    store.git("fetch", "--no-tags", str(bundle), "+refs/heads/*:refs/heads/*")
    store.git("fsck", "--full")
    require(not (restore_dir / "objects/info/alternates").exists(), "restore_has_external_dependencies")
    return {"sha256": digest(bundle), "bytes": bundle.stat().st_size,
            "independent_restore_verified": True, "refs": expected}


def load_plan(path):
    value = json.loads(Path(path).read_text())
    require(value.get("schema") == 1 and value.get("repository") == REPOSITORY
            and value.get("repository_id") == REPOSITORY_ID, "invalid_plan_identity")
    require(isinstance(value.get("candidates"), list), "invalid_plan_candidates")
    require(isinstance(value.get("source_sha"), str) and SHA.fullmatch(value["source_sha"]), "invalid_plan_source")
    for row in value["candidates"]:
        require(valid_branch(row["branch"]) and SHA.fullmatch(row["sha"])
                and row["base"] in PERMANENT and SHA.fullmatch(row["base_sha"]), "invalid_plan_candidate")
    require(len({r["branch"] for r in value["candidates"]}) == len(value["candidates"]), "duplicate_plan_branch")
    return value


def trusted_runtime():
    require(os.environ.get("GITHUB_ACTIONS") == "true", "mutation_requires_github_actions")
    require(os.environ.get("GITHUB_REPOSITORY") == REPOSITORY
            and os.environ.get("GITHUB_REPOSITORY_ID") == str(REPOSITORY_ID), "foreign_workflow_context")
    ref = os.environ.get("GITHUB_WORKFLOW_REF", "")
    require(ref == REPOSITORY + "/" + WORKFLOW + "@refs/heads/main", "untrusted_workflow_ref")
    require(os.environ.get("GITHUB_EVENT_NAME") in {"pull_request_target", "schedule", "workflow_dispatch"}, "untrusted_workflow_event")


def verify_checkout(root, source_sha):
    """Never use a stale checkout's policy after trusted main has advanced."""
    actual = run(["git", "-C", str(root), "rev-parse", "HEAD"]).stdout.strip()
    require(actual == source_sha, "trusted_checkout_is_stale")


def summary(report):
    target = os.environ.get("GITHUB_STEP_SUMMARY")
    if target:
        with Path(target).open("a") as out:
            out.write("### Automatic branch cleanup\n\n")
            out.write(f"Status: **{report.get('status', 'unknown')}**. Deleted: **{len(report.get('deleted', []))}**.\n\n")
            if report.get("error"):
                out.write("Cleanup stopped: `" + report["error"] + "`. Branches were not bypassed.\n\n")
            for branch, reasons in sorted(report.get("held", {}).items()):
                out.write("- `" + branch.replace("`", "") + "`: " + ", ".join(sorted(set(reasons))) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    plan_parser = sub.add_parser("plan")
    plan_parser.add_argument("--output", type=Path, required=True)
    plan_parser.add_argument("--report", type=Path, required=True)
    archive_parser = sub.add_parser("archive")
    archive_parser.add_argument("--plan", type=Path, required=True)
    archive_parser.add_argument("--output-dir", type=Path, required=True)
    apply_parser = sub.add_parser("apply")
    apply_parser.add_argument("--plan", type=Path, required=True)
    apply_parser.add_argument("--report", type=Path, required=True)
    apply_parser.add_argument("--backup-dir", type=Path, required=True)
    apply_parser.add_argument("--backup-artifact-id", type=int, required=True)
    apply_parser.add_argument("--backup-artifact-digest", required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    policy = validate_policy(json.loads((root / ".github/branch-cleanup.json").read_text()))
    github = Github()
    report = {"repository": REPOSITORY, "status": "started", "deleted": []}
    try:
        if args.command == "plan":
            plan = make_plan(github, policy)
            if os.environ.get("GITHUB_ACTIONS") == "true":
                verify_checkout(root, plan["source_sha"])
            write_json(args.output, plan)
            report.update(status="planned", held=plan["held"], candidate_count=plan["candidate_count"])
            if os.environ.get("GITHUB_OUTPUT"):
                with Path(os.environ["GITHUB_OUTPUT"]).open("a") as out:
                    out.write("candidate_count=" + str(plan["candidate_count"]) + "\n")
        elif args.command == "archive":
            trusted_runtime()
            plan = load_plan(args.plan)
            verify_checkout(root, plan["source_sha"])
            github.verify_owner()
            args.output_dir.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix="cleanup-backup-work-", dir=args.output_dir.parent) as temporary:
                directory = Path(temporary)
                store = GitStore(directory / "source.git")
                store.fetch(plan["candidates"])
                bundle = args.output_dir / "recovery.bundle"
                create_bundle(store.path, plan["candidates"], bundle)
                verified = verify_bundle(bundle, plan["candidates"], directory / "restore.git")
                manifest = dict(verified, repository=REPOSITORY, candidates=plan["candidates"],
                                plan_sha256=digest(args.plan), source_sha=plan["source_sha"])
                write_json(args.output_dir / "manifest.json", manifest)
                (args.output_dir / "SHA256SUMS").write_text(verified["sha256"] + "  recovery.bundle\n")
        else:
            trusted_runtime()
            plan = load_plan(args.plan)
            verify_checkout(root, plan["source_sha"])
            report.update(held=plan["held"])
            manifest = json.loads((args.backup_dir / "manifest.json").read_text())
            require(manifest.get("repository") == REPOSITORY and manifest.get("independent_restore_verified") is True,
                    "backup_manifest_invalid")
            require(manifest.get("plan_sha256") == digest(args.plan) and manifest.get("candidates") == plan["candidates"], "backup_plan_mismatch")
            bundle = args.backup_dir / "recovery.bundle"
            require(digest(bundle) == manifest.get("sha256"), "backup_digest_mismatch")
            require(args.backup_artifact_id > 0, "invalid_backup_artifact")
            artifact = github.get("actions/artifacts/" + str(args.backup_artifact_id))
            artifact_digest = args.backup_artifact_digest.removeprefix("sha256:")
            require(re.fullmatch(r"[a-f0-9]{64}", artifact_digest), "invalid_artifact_digest")
            run_id, attempt = int(os.environ["GITHUB_RUN_ID"]), os.environ["GITHUB_RUN_ATTEMPT"]
            require(artifact.get("workflow_run", {}).get("id") == run_id
                    and artifact.get("name") == f"branch-cleanup-backup-{run_id}-{attempt}"
                    and artifact.get("expired") is False and artifact.get("size_in_bytes", 0) > 0
                    and artifact.get("digest") == "sha256:" + artifact_digest, "uploaded_backup_not_verified")
            fresh = make_plan(github, policy)
            require(fresh["source_sha"] == plan["source_sha"] and fresh["policy_sha256"] == plan["policy_sha256"], "trusted_main_or_policy_changed")
            available = {r["branch"]: r for r in fresh["candidates"]}
            selected = [r for r in plan["candidates"] if available.get(r["branch"]) == r]
            for row in plan["candidates"]:
                if row not in selected:
                    report["held"][row["branch"]] = fresh["held"].get(row["branch"], ["state_changed_after_backup"])
            if selected:
                with tempfile.TemporaryDirectory(prefix="cleanup-apply-") as temporary:
                    restore = Path(temporary) / "restore.git"
                    verify_bundle(bundle, plan["candidates"], restore)
                    store = GitStore(restore)
                    store.verify_destination()
                    # Some historical commits need a permission that the
                    # repository GITHUB_TOKEN intentionally does not have.
                    # Keep only those branches; do not block unrelated archives
                    # or introduce a personal-token fallback.
                    archived = []
                    for sha in sorted({r["sha"] for r in selected}):
                        group = [r for r in selected if r["sha"] == sha]
                        try:
                            store.backup_tags(group, github)
                        except CleanupError:
                            for row in group:
                                report["held"][row["branch"]] = ["recovery_tag_not_verified"]
                        else:
                            archived.extend(group)
                    selected = archived
                    # Recheck GitHub ownership/activity/protection after saving the
                    # permanent tags; the SHA lease protects the final ref update.
                    final = make_plan(github, policy)
                    final_candidates = {r["branch"]: r for r in final["candidates"]}
                    require(final["source_sha"] == plan["source_sha"], "trusted_main_changed_before_delete")
                    require(all(final_candidates.get(r["branch"]) == r for r in selected), "activity_changed_before_delete")
                    report["deleted"] = store.delete(selected, github)
                    report["archive_tags"] = [ARCHIVE_PREFIX + r["sha"] for r in selected]
                    report["backup_artifact_id"] = args.backup_artifact_id
            report["status"] = "completed"
    except (CleanupError, OSError, ValueError, KeyError, subprocess.TimeoutExpired) as error:
        report.update(status="blocked", error=str(error) if isinstance(error, CleanupError) else type(error).__name__)
        if getattr(args, "report", None):
            write_json(args.report, report)
        summary(report)
        print("Branch cleanup stopped; inspect its redacted report.")
        return 1
    if getattr(args, "report", None):
        write_json(args.report, report)
        summary(report)
    print(json.dumps({"status": report["status"], "deleted": len(report["deleted"]),
                      "candidate_count": report.get("candidate_count", 0)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
