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
import stat
import subprocess
import tempfile
import threading
import time
import urllib.parse

REPOSITORY = "noah-l-frank/overte"
REPOSITORY_ID = 1319052603
REMOTE = "https://github.com/noah-l-frank/overte.git"
WORKFLOW = ".github/workflows/branch-cleanup.yml"
PERMANENT = {
    "main", "android-main", "android-phone", "android-vr", "android-vr-pico",
    "apple-main", "apple-ios",
}
SCOPES = {
    "main": "main", "android": "android-main", "android-main": "android-main",
    "android-phone": "android-phone", "android-vr": "android-vr",
    "android-pico": "android-vr-pico", "android-vr-pico": "android-vr-pico",
    "apple": "apple-main", "ios": "apple-ios",
}
KINDS = {"feature", "fix", "docs", "refactor", "test", "tests", "task", "ci", "sync", "reconcile", "promote", "build"}
SHA = re.compile(r"^[0-9a-f]{40}$")
# A completion is a wake-up only. These are the declared branch-push owners in
# the seven protected inventories and individually reviewed manual owners.
MANUAL_TERMINAL_WORKFLOW = 386334598
# A newly installed consumer has no predictable numeric registration ID.
# Its one fixed path is authenticated through both live workflow endpoints.
DOCUMENTATION_PUSH_FILENAME = "documentation-push-owner.yml"
DOCUMENTATION_PUSH_TARGETS = frozenset({"main", "android-phone", "android-vr-pico", "apple-ios"})
TERMINAL_WORKFLOWS = {
    330519645: ("Android tests", "android-tests.yml"),
    331117401: ("Android VR integration tests", "android-vr-tests.yml"),
    340529251: ("Branch synchronization", "branch-sync.yml"),
    372770820: ("Owned atomic settings diagnostic", "browser-client-atomic-settings.yml"),
    373796501: ("Direct browser client", "browser-direct-client.yml"),
    349116380: ("CodeQL", "codeql.yml"),
    359712487: ("Dependency release policy", "dependency-releases.yml"),
    331326815: ("Documentation checks", "documentation-checks.yml"),
    330869252: ("iOS bootstrap", "ios-bootstrap.yml"),
    350930890: ("Parent qualification", "parent-qualification.yml"),
    330551824: ("Shared project CI", "project-tests.yml"),
    347471831: ("Workflow security", "workflow-security.yml"),
    386334598: ("Shared sandbox host diagnostic", "shared-sandbox-host-diagnostic.yml"),
    330869250: ("Android Phone trusted build", "android-phone-build.yml"),
    330869251: ("Android Phone emulator acceptance", "android-phone-emulator-acceptance.yml"),
    330556274: ("Android Phone release candidate", "android-phone-release-candidate.yml"),
    371274083: ("Browser client", "browser-client.yml"),
    357615945: ("Issue intake", "issue-intake.yml"),
    367914894: ("Prepare native baseline", "native-dependencies.yml"),
    330643004: ("Pico 4 trusted build", "pico4-build.yml"),
    330644216: ("Pico 4 device acceptance", "pico4-device-acceptance.yml"),
    330643006: ("Pico 4 release candidate", "pico4-release-candidate.yml"),
    366778169: ("Repository checks", "repository-checks.yml"),
    350430503: ("Repository Health Doctor", "repository-health.yml"),
    350930894: ("Sync test reuse", "sync-test-reuse.yml"),
    350930895: ("Sync validation", "sync-validation.yml"),
}
# Six owners support both event types. Event admission is exact rather than a
# manual/push wildcard over the union; the cleanup workflow itself is excluded.
PUSH_TERMINAL_WORKFLOWS = frozenset({
    330519645, 331117401, 340529251, 372770820, 373796501, 349116380,
    359712487, 331326815, 330869252, 350930890, 330551824, 347471831,
})
MANUAL_TERMINAL_WORKFLOWS = frozenset({
    330869250, 330869251, 330556274, 340529251, 372770820, 371274083,
    373796501, 359712487, 331326815, 357615945, 367914894, 330643004,
    330644216, 330643006, 330551824, 366778169, 350430503, 386334598,
    350930894, 350930895,
})


class CleanupError(RuntimeError):
    """An incomplete or unsafe condition; no fallback authorization is implied."""


class CleanupDeferred(CleanupError):
    """Verified concurrent work stopped this attempt before further mutations."""

    def __init__(self, reason, **details):
        super().__init__(reason)
        self.details = details


def api_failure(args, result):
    """Return fixed diagnostic labels; never relay URLs, payloads or stderr."""
    method, family = "GET", "unknown"
    if len(args) > 2 and args[2] == "graphql":
        method, family = "POST", "graphql"
    if "--method" in args:
        index = args.index("--method") + 1
        method = args[index] if index < len(args) and args[index] in {"GET", "POST", "PATCH", "PUT", "DELETE"} else "UNKNOWN"
    prefix = "repos/" + REPOSITORY
    for item in args[2:]:
        if item == prefix or item.startswith(prefix + "/"):
            parts = item[len(prefix):].strip("/").split("?", 1)[0].split("/")
            family = "repository" if parts == [""] else parts[0] if parts[0] in {
                "branches", "pulls", "issues", "compare", "releases", "deployments", "rules", "rulesets", "actions", "git",
            } else "unknown"
            children = {"actions": {"runs", "workflows", "artifacts"}, "git": {"ref", "refs", "commits", "trees", "tags", "blobs"}}
            if family in children and len(parts) > 1 and parts[1] in children[family]:
                family += "_" + parts[1]
            break
    stderr = result.stderr or ""
    if isinstance(stderr, bytes):
        stderr = stderr[:8192].decode("utf-8", errors="replace")
    else:
        stderr = stderr[:8192]
    statuses = re.findall(r"\bHTTP ([1-5][0-9]{2})\b", stderr)
    status = statuses[-1] if statuses else "unknown"
    category = {"401": "unauthorized", "403": "forbidden", "404": "not_found", "409": "conflict",
                "422": "invalid_request", "429": "rate_limited"}.get(status, "server_error" if status.startswith("5")
                                                                       else "cli_error" if status == "unknown" else "http_error")
    if status in {"403", "429"} and any(text in stderr.lower() for text in ("api rate limit exceeded", "secondary rate limit")):
        category = "rate_limited"
    return CleanupError(f"github_api_{method.lower()}_{family}_http_{status}_{category}")


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
        if Path(args[0]).name == "gh" and len(args) > 1 and args[1] == "api":
            raise api_failure(args, result)
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


def branch_inventory(branches):
    require(isinstance(branches, list) and all(
        isinstance(row, dict) and valid_branch(row.get("name"))
        and isinstance(row.get("sha"), str) and SHA.fullmatch(row["sha"])
        and isinstance(row.get("protected"), bool) for row in branches), "invalid_remote_branch_metadata")
    indexed = {row["name"]: row for row in branches}
    require(len(indexed) == len(branches), "duplicate_remote_branch")
    require(PERMANENT <= indexed.keys(), "permanent_branch_missing")
    require(all(indexed[name].get("protected") is True for name in PERMANENT), "permanent_branch_unprotected")
    return indexed


def select_candidates(branches, policy, comparisons, holds=None):
    validate_policy(policy)
    indexed = branch_inventory(branches)
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


class ImmutableReadCache:
    """Private, per-attempt optimization; never a cache of deletion decisions.

    Only trusted cleanup processes may access this directory. The digest detects
    damaged entries; it does not authenticate data from another process, job,
    artifact or cache service. Mutable observations always bypass this class.
    """
    MAX_ENTRY = 3_000_000
    MAX_ENTRIES = 2048
    MAX_BYTES = 64 * 1024 * 1024

    def __init__(self, runner_temp, run_id, attempt):
        require(all(isinstance(value, str) and re.fullmatch(r"[1-9][0-9]*", value)
                    for value in (run_id, attempt)), "invalid_immutable_cache_attempt")
        root = Path(runner_temp)
        require(root.is_absolute() and root == Path(os.path.normpath(root)), "unsafe_immutable_cache_root")
        for current in [*reversed(root.parents), root]:
            info = current.lstat()
            # A trusted sticky temporary directory protects each child entry
            # from other users' rename/unlink operations. Every descendant is
            # still checked for trusted ownership and safe directory modes.
            # Ordinary shared writable ancestors remain unsupported.
            require(stat.S_ISDIR(info.st_mode)
                    and (not info.st_mode & 0o022 or bool(info.st_mode & stat.S_ISVTX))
                    and info.st_uid in {0, os.getuid()}, "unsafe_immutable_cache_ancestor")
        require(root.stat().st_uid == os.getuid(), "foreign_immutable_cache_root")
        self.directory = root / ("branch-cleanup-immutable-" + run_id + "-" + attempt)
        self.directory.mkdir(mode=0o700, exist_ok=True)
        info = self.directory.lstat()
        require(stat.S_ISDIR(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o700
                and info.st_uid == os.getuid(), "unsafe_immutable_cache_directory")
        self.context = {"repository": REPOSITORY, "repository_id": REPOSITORY_ID,
                        "run_id": run_id, "attempt": attempt,
                        "controller": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
        self.locks, self.guard = {}, threading.Lock()

    @staticmethod
    def canonical(value):
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()

    @staticmethod
    def blob_identity(raw):
        # Public Git object encoding, never a checksum of secret material.
        # Fixed Git with no filters/-w, no inherited configuration and no
        # candidate cwd cannot run checkout filters or modify an object store.
        require(type(raw) is bytes and len(raw) <= 1_500_000, "workflow_content_too_large")
        try:
            result = subprocess.run(["/usr/bin/git", "--no-replace-objects", "hash-object", "--no-filters", "--stdin"],
                cwd="/", input=raw, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10, check=True,
                env={"PATH": "/usr/bin:/bin", "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null"})
            value = result.stdout.decode("ascii").strip()
        except (OSError, UnicodeError, subprocess.SubprocessError):
            raise CleanupError("workflow_git_object_encoding_unavailable") from None
        require(SHA.fullmatch(value), "invalid_workflow_git_object_encoding")
        return value

    @staticmethod
    def request(suffix, paginate):
        if paginate:
            return None
        # Fixed query spelling excludes branch refs, arbitrary parameters and
        # API listings whose completeness or membership can change over time.
        if re.fullmatch(r"compare/[0-9a-f]{40}\.\.\.[0-9a-f]{40}\?per_page=1", suffix):
            return {"kind": "compare", "endpoint": suffix}
        match = re.fullmatch(r"contents/(\.github/workflows(?:/[^?]+)?)\?ref=([0-9a-f]{40})", suffix)
        if match:
            path = urllib.parse.unquote(match[1])
            name = path.removeprefix(".github/workflows/")
            if (path == ".github/workflows" or
                    path.startswith(".github/workflows/") and "/" not in name
                    and name not in {"", ".", ".."} and path.endswith((".yml", ".yaml"))):
                if not any(char in path for char in "\r\n\0\\") and urllib.parse.quote(path, safe="/") == match[1]:
                    return {"kind": "contents", "endpoint": suffix}
        return None

    @staticmethod
    def validate(request, value):
        if request["kind"] == "compare":
            require(isinstance(value, dict) and value.get("status") in {"ahead", "behind", "identical", "diverged"}
                    and type(value.get("behind_by")) is int and value["behind_by"] >= 0
                    and isinstance(value.get("merge_base_commit"), dict)
                    and isinstance(value["merge_base_commit"].get("sha"), str)
                    and SHA.fullmatch(value["merge_base_commit"]["sha"]), "invalid_cached_immutable_compare")
        else:
            path = urllib.parse.unquote(request["endpoint"].split("?", 1)[0][9:])
            if path == ".github/workflows":
                require(isinstance(value, list) and len(value) < 1000, "invalid_cached_workflow_directory")
                seen = set()
                for item in value:
                    name = item.get("path") if isinstance(item, dict) else None
                    require(isinstance(name, str) and name.startswith(path + "/") and "/" not in name[len(path) + 1:]
                            and name[len(path) + 1:] not in {"", ".", ".."}
                            and not any(char in name for char in "\r\n\0") and name not in seen,
                            "invalid_cached_workflow_directory_entry")
                    seen.add(name)
                    if name.endswith((".yml", ".yaml")):
                        require(item.get("type") == "file" and isinstance(item.get("sha"), str)
                                and SHA.fullmatch(item["sha"]), "invalid_cached_workflow_file_entry")
            else:
                require(isinstance(value, dict) and value.get("path") == path and value.get("type") == "file"
                        and value.get("encoding") == "base64" and isinstance(value.get("content"), str)
                        and len(value["content"]) <= 2_000_000 and isinstance(value.get("sha"), str)
                        and SHA.fullmatch(value["sha"]) and "target" not in value and "submodule_git_url" not in value,
                        "invalid_cached_workflow_content")
                import base64
                import binascii
                try:
                    raw = base64.b64decode(re.sub(rb"[ \t\r\n]", b"", value["content"].encode("ascii")), validate=True)
                    raw.decode("utf-8")
                except (ValueError, UnicodeError, binascii.Error):
                    raise CleanupError("invalid_cached_workflow_encoding") from None
                require(ImmutableReadCache.blob_identity(raw) == value["sha"],
                        "cached_workflow_blob_mismatch")
                require("size" not in value or type(value["size"]) is int and value["size"] == len(raw),
                        "cached_workflow_size_mismatch")

    @staticmethod
    def project(request, value):
        # Exact Git identities do not freeze account metadata or API URLs.
        # Return only the immutable facts used by cleanup, on misses AND hits.
        if request["kind"] == "compare":
            return {"status": value["status"], "behind_by": value["behind_by"],
                    "merge_base_commit": {"sha": value["merge_base_commit"]["sha"]}}
        if isinstance(value, list):
            return [{key: item[key] for key in ("path", "type", "sha") if key in item} for item in value]
        return {key: value[key] for key in ("path", "type", "sha", "encoding", "content", "size") if key in value}

    def _read(self, path, request):
        try:
            descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(descriptor, "rb") as stream:
                info = os.fstat(stream.fileno())
                require(stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o600
                        and info.st_uid == os.getuid() and info.st_nlink == 1 and info.st_size <= self.MAX_ENTRY,
                        "unsafe_immutable_cache_entry")
                data = stream.read(self.MAX_ENTRY + 1)
            require(len(data) <= self.MAX_ENTRY, "oversized_immutable_cache_entry")
            def unique(pairs):
                result = {}
                for key, value in pairs:
                    require(key not in result, "duplicate_immutable_cache_field")
                    result[key] = value
                return result
            entry = json.loads(data, object_pairs_hook=unique)
            require(isinstance(entry, dict) and set(entry) == {"schema", "context", "request", "value", "digest"}
                    and type(entry["schema"]) is int and entry["schema"] == 1
                    and entry["context"] == self.context and entry["request"] == request,
                    "foreign_immutable_cache_entry")
            claimed = entry.pop("digest")
            require(claimed == hashlib.sha256(self.canonical(entry)).hexdigest(), "damaged_immutable_cache_entry")
            self.validate(request, entry["value"])
            return self.project(request, entry["value"])
        except (CleanupError, OSError, ValueError, TypeError, KeyError):
            return None  # A damaged entry grants no permission; fetch again.

    def _write(self, path, request, value):
        # Capacity inspection and atomic writes share a short filesystem lock;
        # immutable network reads for different keys remain concurrent.
        with self.guard:
            self._write_locked(path, request, value)

    def _write_locked(self, path, request, value):
        entry = {"schema": 1, "context": self.context, "request": request, "value": value}
        entry["digest"] = hashlib.sha256(self.canonical(entry)).hexdigest()
        data = self.canonical(entry)
        if len(data) > self.MAX_ENTRY:
            return
        try:
            total, count = 0, 0
            for item in self.directory.iterdir():
                count += 1
                total += item.lstat().st_size
                if count >= self.MAX_ENTRIES or total + len(data) > self.MAX_BYTES:
                    return
            with tempfile.NamedTemporaryFile(dir=self.directory, delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(data)
            try:
                temporary.replace(path)
            finally:
                temporary.unlink(missing_ok=True)
        except OSError:
            pass  # A full/unavailable cache cannot replace fresh API evidence.

    def get(self, request, fetch, observe=None):
        info = self.directory.lstat()
        require(stat.S_ISDIR(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o700
                and info.st_uid == os.getuid(), "unsafe_immutable_cache_directory")
        key = hashlib.sha256(self.canonical(request)).hexdigest()
        with self.guard:
            lock = (None if key not in self.locks and len(self.locks) >= self.MAX_ENTRIES
                    else self.locks.setdefault(key, threading.Lock()))
        if lock is None:
            if observe:
                observe(False)
            value = fetch()
            self.validate(request, value)
            return self.project(request, value)
        with lock:
            path = self.directory / (key + ".json")
            value = self._read(path, request)
            if observe:
                observe(value is not None)
            if value is None:
                value = fetch()
                self.validate(request, value)
                value = self.project(request, value)
                self._write(path, request, value)
            return value


class Github:
    def __init__(self):
        self.cache = None
        self.cache_checked = False
        self._cache_statistics = {"state": "disabled", "hits": 0, "misses": 0,
                                  "fresh_api_invocations": {"contents": 0, "compare": 0, "other": 0}}
        self._statistics_lock = threading.Lock()

    def cache_statistics(self):
        """Per-client CLI call counters, never HTTP page or quota measurements."""
        with self._statistics_lock:
            return {**self._cache_statistics,
                    "fresh_api_invocations": dict(self._cache_statistics["fresh_api_invocations"])}

    def _observe_cache(self, hit):
        with self._statistics_lock:
            self._cache_statistics["hits" if hit else "misses"] += 1

    def get(self, suffix="", paginate=False):
        require(not suffix.startswith(("/", "http"))
                and not {".", ".."}.intersection(suffix.split("?", 1)[0].split("/")), "unsafe_api_path")
        endpoint = "repos/" + REPOSITORY + ("/" + suffix if suffix else "")
        with self._statistics_lock:
            if not self.cache_checked:
                enabled = os.environ.get("BRANCH_CLEANUP_IMMUTABLE_CACHE", "")
                require(enabled in {"", "1"}, "invalid_immutable_cache_switch")
                if enabled:
                    trusted_runtime()
                    run_id, attempt = os.environ.get("GITHUB_RUN_ID", ""), os.environ.get("GITHUB_RUN_ATTEMPT", "")
                    require(all(re.fullmatch(r"[1-9][0-9]*", value) for value in (run_id, attempt)), "invalid_immutable_cache_attempt")
                    try:
                        self.cache = ImmutableReadCache(os.environ.get("RUNNER_TEMP", ""), run_id, attempt)
                        self._cache_statistics["state"] = "enabled"
                    except (CleanupError, OSError):
                        # Optional cache provisioning cannot invalidate fresh API
                        # evidence. Only initialization is optional; API failures,
                        # invalid responses and all ordinary guards remain fatal.
                        self.cache = None
                        self._cache_statistics["state"] = "unavailable"
                self.cache_checked = True
        request = ImmutableReadCache.request(suffix, paginate)
        kind = request["kind"] if request is not None else "other"
        if self.cache is not None and request is not None:
            return self.cache.get(request, lambda: self._get(endpoint, paginate, kind), self._observe_cache)
        return self._get(endpoint, paginate, kind)

    def _get(self, endpoint, paginate, kind):
        args = ["gh", "api", "--method", "GET", endpoint]
        if paginate:
            args += ["--paginate", "--slurp"]
        with self._statistics_lock:
            self._cache_statistics["fresh_api_invocations"][kind] += 1
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

    def release_tag_commit(self, name):
        """Resolve an existing release tag without following foreign object URLs."""
        if (not isinstance(name, str) or not name
                or run(["git", "check-ref-format", "refs/tags/" + name], check=False).returncode):
            return None
        reference = self.get("git/ref/tags/" + urllib.parse.quote(name, safe=""))
        if not isinstance(reference, dict) or reference.get("ref") != "refs/tags/" + name:
            return None
        obj, seen = reference.get("object"), set()
        for depth in range(9):
            if not isinstance(obj, dict) or not isinstance(obj.get("sha"), str) or not SHA.fullmatch(obj["sha"]):
                return None
            oid = obj["sha"]
            if obj.get("type") == "commit":
                return oid
            if obj.get("type") != "tag" or oid in seen or depth == 8:
                return None
            seen.add(oid)
            annotation = self.get("git/tags/" + oid)
            if not isinstance(annotation, dict) or annotation.get("sha") != oid:
                return None
            obj = annotation.get("object")
        return None

    def active_run_pages(self):
        endpoints = ["actions/runs?status=" + status + "&per_page=100" for status in
                     ["queued", "in_progress", "waiting", "pending", "requested"]]
        # GitHub can briefly return a count from one index snapshot and rows
        # from another when jobs change state. Retry the entire inventory; an
        # incomplete response never supplies permission to merge or delete.
        for delay in (0, 2, 5, 10):
            if delay:
                time.sleep(delay)
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
                pages = list(pool.map(lambda endpoint: self.get(endpoint, paginate=True), endpoints))
            for page in pages:
                require(isinstance(page, dict) and type(page.get("total_count")) is int
                        and page["total_count"] >= 0 and isinstance(page.get("workflow_runs"), list),
                        "active_run_listing_invalid")
            if all(page["total_count"] == len(page["workflow_runs"]) for page in pages):
                return pages
        raise CleanupError("active_run_listing_incomplete")

    def activity_holds(self, candidates, policy):
        names = {r["branch"] for r in candidates}
        held = self.open_pr_holds(names)
        if not names:
            return held
        own_run = int(os.environ.get("GITHUB_RUN_ID", "0"))
        active = []
        for page in self.active_run_pages():
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
            head = urllib.parse.quote("noah-l-frank:" + row["branch"], safe="")
            prs = self.get("pulls?state=all&head=" + head + "&per_page=100", paginate=True)
            if any(policy["keep_label"] in {label["name"] for label in pr.get("labels", [])} for pr in prs):
                held.setdefault(row["branch"], []).append("keep_branch_label")
        for entry in self.get("deployments?per_page=100", paginate=True):
            value = entry.get("ref", "")
            for row in candidates:
                if value in {row["branch"], "refs/heads/" + row["branch"], row["sha"]}:
                    held.setdefault(row["branch"], []).append("deployment_reference")
        for entry in self.get("releases?per_page=100", paginate=True):
            value = entry.get("target_commitish", "")
            # Candidates already have complete ancestry proof. make_plan still
            # requires deletion/non-fast-forward protection on their targets.
            # A named branch consumer remains a hold; only an exact commit also
            # retained by its actual release tag can be independent of the ref.
            tagged_commit = (self.release_tag_commit(entry.get("tag_name"))
                             if value in {row["sha"] for row in candidates} else None)
            for row in candidates:
                if (value in {row["branch"], "refs/heads/" + row["branch"], row["sha"]}
                        and not (value == row["sha"] == tagged_commit)):
                    held.setdefault(row["branch"], []).append("release_reference")
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
            actual = ImmutableReadCache.blob_identity(raw)
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
    return {"schema": 1, "repository": REPOSITORY, "repository_id": REPOSITORY_ID,
            "source_sha": indexed["main"]["sha"], "policy_sha256": hashlib.sha256(json.dumps(policy, sort_keys=True).encode()).hexdigest(),
            "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "candidates": candidates, "held": held, "candidate_count": len(candidates)}


def same_repository(value):
    return (isinstance(value, dict) and value.get("full_name") == REPOSITORY
            and type(value.get("id")) is int and value["id"] == REPOSITORY_ID)


def terminal_run(github, event):
    """Authenticate one finite completion; its conclusion proves no integration."""
    require(isinstance(event, dict) and event.get("action") == "completed"
            and same_repository(event.get("repository")), "invalid_terminal_event_repository")
    signal = event.get("workflow_run")
    require(isinstance(signal, dict) and type(signal.get("id")) is int and signal["id"] > 0
            and type(signal.get("run_attempt")) is int and signal["run_attempt"] > 0
            and same_repository(signal.get("head_repository")),
            "invalid_terminal_run_identity")
    actual = github.get("actions/runs/" + str(signal["id"]))
    fields = ("id", "run_attempt", "workflow_id", "event", "status", "head_branch", "head_sha", "name")
    require(isinstance(actual, dict) and all(actual.get(key) == signal.get(key) for key in fields)
            and type(actual.get("id")) is int and type(actual.get("run_attempt")) is int
            and type(actual.get("workflow_id")) is int and actual["workflow_id"] > 0
            and same_repository(actual.get("repository")) and same_repository(actual.get("head_repository"))
            and (actual["workflow_id"] != MANUAL_TERMINAL_WORKFLOW or actual.get("head_branch") == "main")
            and actual.get("status") == "completed"
            and isinstance(actual.get("conclusion"), str) and bool(actual["conclusion"])
            and isinstance(actual.get("name"), str) and bool(actual["name"])
            and actual.get("head_branch") in PERMANENT and isinstance(actual.get("head_sha"), str)
            and SHA.fullmatch(actual["head_sha"]), "invalid_terminal_push_run")
    registered_documentation = False
    if actual["workflow_id"] in TERMINAL_WORKFLOWS:
        name, filename = TERMINAL_WORKFLOWS[actual["workflow_id"]]
    else:
        name, filename = "Documentation checks", DOCUMENTATION_PUSH_FILENAME
        require(actual.get("event") == "push" and actual["head_branch"] in DOCUMENTATION_PUSH_TARGETS
                and actual.get("name") == name and actual.get("path") == ".github/workflows/" + filename,
                "unreviewed_terminal_workflow")
        registration = github.get("actions/workflows/" + filename)
        require(isinstance(registration, dict) and type(registration.get("id")) is int
                and registration["id"] == actual["workflow_id"] and registration.get("name") == name
                and registration.get("path") == actual["path"] and registration.get("state") == "active",
                "terminal_documentation_registration_changed")
        registered_documentation = True
    require((actual.get("event") == "push" and (actual["workflow_id"] in PUSH_TERMINAL_WORKFLOWS
                                               or registered_documentation))
            or (actual.get("event") == "workflow_dispatch"
                and actual["workflow_id"] in MANUAL_TERMINAL_WORKFLOWS), "invalid_terminal_push_run")
    path = ".github/workflows/" + filename
    require(actual.get("path") == path, "unreviewed_terminal_workflow")
    workflow = github.get("actions/workflows/" + str(actual["workflow_id"]))
    require(isinstance(workflow, dict) and workflow.get("id") == actual["workflow_id"]
            and workflow.get("name") == name and workflow.get("path") == path,
            "terminal_workflow_registration_changed")
    require(not registered_documentation or workflow.get("state") == "active",
            "terminal_documentation_registration_changed")
    # The run API may put the dynamic YAML run-name in `name`. Authenticate the
    # static workflow name through its fixed registration, not that display text.
    return dict(actual, registered_workflow_name=name)


def terminal_retry(github, policy, event):
    """Return a fresh closed-PR hint, never a deletion plan or ancestry proof.

    Any authenticated completion may retry after activity clears. Electing a
    latest event loses wake-ups when delivery and pending replacement reorder.
    """
    validate_policy(policy)
    github.verify_owner()
    actual = terminal_run(github, event)
    indexed = branch_inventory(github.branches())
    target, trigger_revision = actual["head_branch"], actual["head_sha"]
    revision = indexed[target]["sha"]
    result = {"retry": False, "source_sha": indexed["main"]["sha"], "target": target,
              "trigger_run": actual["id"], "trigger_attempt": actual["run_attempt"],
              "trigger_source_sha": trigger_revision, "target_sha": revision, "hint_count": 0}
    if trigger_revision != revision:
        comparison = github.get("compare/" + trigger_revision + "..." + revision + "?per_page=1")
        require(isinstance(comparison, dict) and isinstance(comparison.get("status"), str)
                and comparison["status"] in {"ahead", "behind", "identical", "diverged"}
                and type(comparison.get("behind_by")) is int and comparison["behind_by"] >= 0
                and isinstance(comparison.get("merge_base_commit"), dict)
                and isinstance(comparison["merge_base_commit"].get("sha"), str)
                and SHA.fullmatch(comparison["merge_base_commit"]["sha"]), "invalid_terminal_source_ancestry")
        if (comparison["status"] != "ahead" or comparison["behind_by"] != 0
                or comparison["merge_base_commit"]["sha"] != trigger_revision):
            return dict(result, reason="terminal_source_not_retained")
    path = actual["path"]
    endpoint = "contents/" + path + "?ref=" + trigger_revision
    content = github.get(endpoint)
    ImmutableReadCache.validate(ImmutableReadCache.request(endpoint, False), content)
    import base64
    source = base64.b64decode(re.sub(rb"[ \t\r\n]", b"", content["content"].encode("ascii"))).decode("utf-8")
    name = actual["registered_workflow_name"]
    names = "|".join(re.escape(value) for value in (name, "'" + name + "'", '"' + name + '"'))
    require(len(re.findall(r"(?m)^name:[ \t]*(?:" + names + r")[ \t]*(?:#.*)?$", source)) == 1,
            "terminal_workflow_source_name_changed")
    held = github.open_pr_holds(set(indexed))
    hints = []
    for branch, row in sorted(indexed.items()):
        if (row["protected"] or branch in PERMANENT or branch in policy["holds"]
                or branch in held or scope_target(branch) != target):
            continue
        head = urllib.parse.quote("noah-l-frank:" + branch, safe="")
        prs = github.get("pulls?state=closed&head=" + head + "&base="
                         + urllib.parse.quote(target, safe="") + "&per_page=100", paginate=True)
        require(isinstance(prs, list) and all(isinstance(pr, dict)
                and isinstance(pr.get("head"), dict) and isinstance(pr.get("base"), dict) for pr in prs),
                "invalid_terminal_closed_pr_inventory")
        # Earlier closed PRs can remain CI-held across later merges. The event's
        # pull_requests array is not an inventory of these current topic refs.
        if any(pr.get("state") == "closed" and isinstance(pr.get("closed_at"), str) and pr["closed_at"]
               and same_repository(pr.get("head", {}).get("repo"))
               and same_repository(pr.get("base", {}).get("repo"))
               and pr["head"].get("ref") == branch and pr["head"].get("sha") == row["sha"]
               and pr["base"].get("ref") == target for pr in prs):
            hints.append({"branch": branch, "sha": row["sha"], "base": target, "base_sha": revision})
    if not hints:
        return dict(result, reason="no_current_closed_pr_hint")
    activity = github.activity_holds(hints, policy)
    hints = [row for row in hints if row["branch"] not in activity]
    if not hints:
        return dict(result, reason="terminal_candidates_still_held")
    reference = github.get("git/ref/heads/" + urllib.parse.quote(target, safe=""))
    require(isinstance(reference, dict) and reference.get("ref") == "refs/heads/" + target
            and isinstance(reference.get("object"), dict) and reference["object"].get("type") == "commit"
            and isinstance(reference["object"].get("sha"), str) and SHA.fullmatch(reference["object"]["sha"]),
            "invalid_terminal_current_target")
    if reference["object"]["sha"] != revision:
        return dict(result, reason="terminal_target_changed")
    return dict(result, retry=True, hint_count=len(hints), reason="current_closed_pr_retry")


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

    def delete(self, candidates, github):
        if not candidates:
            return []
        require(all(valid_branch(r.get("branch")) and isinstance(r.get("sha"), str)
                    and SHA.fullmatch(r["sha"]) for r in candidates), "invalid_delete_candidate")
        require(len({r["branch"] for r in candidates}) == len(candidates), "duplicate_delete_candidate")
        require(all(r["branch"] not in PERMANENT and scope_target(r["branch"]) for r in candidates), "protected_or_unmanaged_delete")
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
    require(os.environ.get("GITHUB_EVENT_NAME") in {"pull_request_target", "schedule", "workflow_dispatch", "workflow_run"}, "untrusted_workflow_event")


def record_cache_statistics(report, github):
    # Only the trusted adapter's internal counters are retained. Old offline
    # fakes need not implement telemetry; arbitrary API values are never used.
    if type(getattr(github, "_cache_statistics", None)) is dict:
        report["immutable_api_cache"] = github.cache_statistics()


def verify_checkout(root, source_sha):
    """Never use a stale checkout's policy after trusted main has advanced."""
    actual = run(["git", "-C", str(root), "rev-parse", "HEAD"]).stdout.strip()
    require(actual == source_sha, "trusted_checkout_is_stale")


def defer_main_change(github, previous, observed, reason):
    """A mismatch is quiet only when both snapshots are retained by current main."""
    require(previous != observed and all(isinstance(sha, str) and SHA.fullmatch(sha)
                                        for sha in (previous, observed)), reason)
    github.verify_owner()
    reference = github.get("git/ref/heads/main")
    require(isinstance(reference, dict) and isinstance(reference.get("object"), dict), "invalid_current_main")
    current = reference["object"].get("sha")
    require(isinstance(current, str) and SHA.fullmatch(current), "invalid_current_main")
    for revision in dict.fromkeys((previous, observed)):
        if revision == current:
            continue
        comparison = github.get(f"compare/{revision}...{current}?per_page=1")
        require(isinstance(comparison, dict) and comparison.get("status") == "ahead"
                and type(comparison.get("behind_by")) is int and comparison["behind_by"] == 0
                and isinstance(comparison.get("merge_base_commit"), dict)
                and comparison["merge_base_commit"].get("sha") == revision, reason)
    raise CleanupDeferred(reason, previous_main_sha=previous,
                          observed_main_sha=observed, current_main_sha=current)


def verify_current_checkout(root, source_sha, github):
    actual = run(["git", "-C", str(root), "rev-parse", "HEAD"]).stdout.strip()
    if actual != source_sha:
        defer_main_change(github, actual, source_sha, "trusted_checkout_is_stale")


def mark_deferred(report, error):
    report.update(status="deferred", reason=str(error), deferred_details=error.details)


def summary(report):
    target = os.environ.get("GITHUB_STEP_SUMMARY")
    if target:
        with Path(target).open("a") as out:
            out.write("### Automatic branch cleanup\n\n")
            out.write(f"Status: **{report.get('status', 'unknown')}**. Deleted: **{len(report.get('deleted', []))}**.\n\n")
            if report.get("error"):
                out.write("Cleanup stopped: `" + report["error"] + "`. Branches were not bypassed.\n\n")
            if report.get("status") == "deferred":
                out.write("Expected deferral: `" + report["reason"]
                          + "`. The next wake-up reassesses current state.\n\n")
            for branch, reasons in sorted(report.get("held", {}).items()):
                out.write("- `" + branch.replace("`", "") + "`: " + ", ".join(sorted(set(reasons))) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    retry_parser = sub.add_parser("retry")
    retry_parser.add_argument("--event", type=Path, required=True)
    retry_parser.add_argument("--output", type=Path, required=True)
    retry_parser.add_argument("--report", type=Path, required=True)
    plan_parser = sub.add_parser("plan")
    plan_parser.add_argument("--output", type=Path, required=True)
    plan_parser.add_argument("--report", type=Path, required=True)
    backup_parser = sub.add_parser("backup")
    backup_parser.add_argument("--plan", type=Path, required=True)
    backup_parser.add_argument("--output-dir", type=Path, required=True)
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
        if args.command == "retry":
            trusted_runtime()
            require(os.environ.get("GITHUB_EVENT_NAME") == "workflow_run", "invalid_terminal_runner_event")
            result = terminal_retry(github, policy, json.loads(args.event.read_text()))
            verify_current_checkout(root, result["source_sha"], github)
            report.update(result, status="retry-ready" if result["retry"] else "retry-held")
        elif args.command == "plan":
            plan = make_plan(github, policy)
            if os.environ.get("GITHUB_ACTIONS") == "true":
                verify_current_checkout(root, plan["source_sha"], github)
            write_json(args.output, plan)
            report.update(status="planned", held=plan["held"], candidate_count=plan["candidate_count"])
        elif args.command == "backup":
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
            require(fresh["policy_sha256"] == plan["policy_sha256"], "trusted_main_or_policy_changed")
            if fresh["source_sha"] != plan["source_sha"]:
                defer_main_change(github, plan["source_sha"], fresh["source_sha"], "trusted_main_or_policy_changed")
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
                    # Recheck activity, ancestry, and target protection after the
                    # independent restore; exact SHA leases guard the ref update.
                    final = make_plan(github, policy)
                    final_candidates = {r["branch"]: r for r in final["candidates"]}
                    if final["source_sha"] != plan["source_sha"]:
                        defer_main_change(github, plan["source_sha"], final["source_sha"], "trusted_main_changed_before_delete")
                    if not all(final_candidates.get(r["branch"]) == r for r in selected):
                        for row in selected:
                            if final_candidates.get(row["branch"]) != row:
                                report["held"][row["branch"]] = final["held"].get(
                                    row["branch"], ["state_changed_after_backup"])
                        raise CleanupDeferred("activity_changed_before_delete")
                    report["deleted"] = store.delete(selected, github)
                    report["backup_artifact_id"] = args.backup_artifact_id
            report["status"] = "completed"
    except CleanupDeferred as error:
        mark_deferred(report, error)
        if args.command == "plan":
            args.output.unlink(missing_ok=True)
            report["candidate_count"] = 0
    except (CleanupError, OSError, ValueError, KeyError, subprocess.TimeoutExpired) as error:
        record_cache_statistics(report, github)
        report.update(status="blocked", error=str(error) if isinstance(error, CleanupError) else type(error).__name__)
        if getattr(args, "report", None):
            write_json(args.report, report)
        summary(report)
        print("Branch cleanup stopped; inspect its redacted report.")
        return 1
    if args.command == "retry":
        with args.output.open("a") as out:
            out.write("retry=" + str(report["status"] == "retry-ready" and report.get("retry") is True).lower() + "\n")
    if args.command == "plan" and os.environ.get("GITHUB_OUTPUT"):
        with Path(os.environ["GITHUB_OUTPUT"]).open("a") as out:
            out.write("candidate_count=" + str(report["candidate_count"]) + "\n")
            out.write("deferred=" + str(report["status"] == "deferred").lower() + "\n")
    record_cache_statistics(report, github)
    if getattr(args, "report", None):
        write_json(args.report, report)
        summary(report)
    print(json.dumps({"status": report["status"], "deleted": len(report["deleted"]),
                      "candidate_count": report.get("candidate_count", 0)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
