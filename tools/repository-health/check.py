#!/usr/bin/env python3
"""Fail-closed, read-only audit of Overte repository governance and security."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen
import argparse
import importlib.util
import json
import os
import re
import sys

try:
    import yaml
except ImportError:  # pragma: no cover - exercised only on an incomplete runner image
    yaml = None


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / ".github/repository-health.json"
DEFAULT_REPORT = ROOT / "repository-health-report.json"
AREAS = (
    "branches", "issues", "labels", "task_branches", "workflows", "security",
    "repository_contracts",
)
WORKFLOW_LABEL = re.compile(r"^workflow: ")
TASK_BRANCH = re.compile(
    r"^task/(?P<scope>[a-z0-9]+(?:-[a-z0-9]+)*)/"
    r"(?P<issue>[1-9][0-9]*)-(?P<slug>[a-z0-9]+(?:-[a-z0-9]+)*)$"
)
REMOTE_ACTION = re.compile(r"^\s*-?\s*uses:\s*([^\s#]+)", re.MULTILINE)
FULL_PIN = re.compile(r"^[^@\s]+@[0-9a-f]{40}$")
SENSITIVE = re.compile(
    r"(?i)(bearer\s+[a-z0-9._-]+|gh[pousr]_[a-z0-9]+|github_token\s*[:=]\s*\S+)"
)


class AuditError(RuntimeError):
    """A check cannot safely determine its result."""


class PermissionUnknown(AuditError):
    """GitHub did not permit a required read-only query."""


@dataclass(frozen=True)
class Finding:
    code: str
    message: str


class GitHubApi:
    """Small read-only GitHub API client with bounded pagination."""

    def __init__(self, token: str):
        if not token:
            raise AuditError("GITHUB_TOKEN is required for a live audit")
        self.token = token

    def _open(self, path: str, payload: dict[str, Any] | None = None) -> tuple[Any, Any]:
        url = path if path.startswith("https://api.github.com/") else "https://api.github.com/" + path.lstrip("/")
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = Request(
            url,
            data=data,
            method="GET" if payload is None else "POST",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "overte-repository-health-doctor",
                "Content-Type": "application/json",
            },
        )
        try:
            with urlopen(request, timeout=30) as response:
                return json.load(response), response.headers
        except HTTPError as error:
            if error.code == 403 and error.headers.get("X-RateLimit-Remaining") != "0":
                raise PermissionUnknown(
                    f"read-only GitHub API permission unavailable (HTTP {error.code})"
                ) from error
            if error.code == 403:
                raise AuditError("GitHub API rate limit exhausted (HTTP 403)") from error
            raise AuditError(f"GitHub API request failed (HTTP {error.code})") from error
        except (URLError, TimeoutError, json.JSONDecodeError) as error:
            raise AuditError(f"GitHub API request failed ({type(error).__name__})") from error

    def _request(self, path: str, payload: dict[str, Any] | None = None) -> Any:
        document, _headers = self._open(path, payload)
        return document

    def get(self, path: str) -> Any:
        return self._request(path)

    def pages(self, path: str, limit: int = 100) -> list[Any]:
        separator = "&" if "?" in path else "?"
        next_path: str | None = f"{path}{separator}per_page={limit}"
        output: list[Any] = []
        for _page in range(100):
            if next_path is None:
                return output
            document, headers = self._open(next_path)
            if not isinstance(document, list):
                raise AuditError("paginated GitHub API response is not a list")
            output.extend(document)
            next_path = None
            for entry in (headers.get("Link") or "").split(","):
                match = re.match(r'\s*<([^>]+)>;\s*rel="([^"]+)"', entry)
                if not match or match.group(2) != "next":
                    continue
                parsed = urlsplit(match.group(1))
                if parsed.scheme != "https" or parsed.netloc != "api.github.com":
                    raise AuditError("GitHub pagination returned an unexpected target")
                next_path = match.group(1)
            if next_path is None:
                return output
        raise AuditError("GitHub API pagination exceeded 100 pages")

    def pinned_issue_numbers(self, owner: str, repository: str) -> set[int]:
        query = """query($owner:String!,$name:String!){repository(owner:$owner,name:$name){pinnedIssues(first:10){nodes{issue{number}}}}}"""
        document = self._request(
            "graphql", {"query": query, "variables": {"owner": owner, "name": repository}}
        )
        try:
            nodes = document["data"]["repository"]["pinnedIssues"]["nodes"]
            return {node["issue"]["number"] for node in nodes}
        except (KeyError, TypeError) as error:
            raise AuditError("GitHub GraphQL returned invalid pinned-Issue data") from error


class Doctor:
    def __init__(self, root: Path, config: dict[str, Any], api: Any | None = None):
        self.root = root
        self.config = config
        self.api = api
        self.findings: dict[str, list[Finding]] = {area: [] for area in AREAS}
        self.data: dict[str, Any] = {area: {} for area in AREAS}
        self._issues: list[dict[str, Any]] | None = None
        self._workflows: list[dict[str, Any]] | None = None

    def fail(self, area: str, code: str, message: str) -> None:
        self.findings[area].append(Finding(code, redact(message)))

    def _guard(self, area: str, function: Any) -> None:
        try:
            function()
        except PermissionUnknown as error:
            self.fail(area, "UNKNOWN_PERMISSION", str(error))
        except (AuditError, OSError, ValueError, KeyError, TypeError) as error:
            self.fail(area, "CHECK_ERROR", str(error))

    def live(self) -> dict[str, Any]:
        if self.api is None:
            raise AuditError("live audit needs an API client")
        for area, function in (
            ("branches", self.check_branches),
            ("issues", self.check_issues),
            ("labels", self.check_labels),
            ("task_branches", self.check_task_branches),
            ("workflows", self.check_workflows),
            ("security", self.check_security),
            ("repository_contracts", self.check_contracts),
        ):
            self._guard(area, function)
        return self.report("live")

    def local(self) -> dict[str, Any]:
        self._guard("repository_contracts", self.check_contracts)
        return self.report("local")

    def report(self, mode: str) -> dict[str, Any]:
        results = {}
        for area in AREAS:
            results[area] = {
                "status": "FAIL" if self.findings[area] else "PASS",
                "findings": [asdict(item) for item in self.findings[area]],
                "data": self.data[area],
            }
        has_operational_error = any(
            finding.code in {"CHECK_ERROR", "STARTUP_ERROR", "UNKNOWN_PERMISSION", "SECURITY_API_ERROR"}
            for findings in self.findings.values()
            for finding in findings
        )
        status = "FAIL" if any(self.findings.values()) else "PASS"
        return {
            "schema": 1,
            "mode": mode,
            "repository": self.config["repository"],
            "status": status,
            "exit_code": 0 if status == "PASS" else (2 if has_operational_error else 1),
            "results": results,
        }

    def policy(self) -> dict[str, Any]:
        path = self.root / ".github/branch-policy.json"
        spec = importlib.util.spec_from_file_location("repository_health_branch_policy", self.root / "tools/branch-policy/check.py")
        if not spec or not spec.loader:
            raise AuditError("cannot load branch-policy checker")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module.load_policy(path)

    def all_issues(self) -> list[dict[str, Any]]:
        if self._issues is None:
            self._issues = self.api.pages(
                f"repos/{self.config['repository']}/issues?state=all"
            )
        return self._issues

    def all_workflows(self) -> list[dict[str, Any]]:
        if self._workflows is None:
            document = self.api.get(f"repos/{self.config['repository']}/actions/workflows?per_page=100")
            workflows = document.get("workflows") if isinstance(document, dict) else None
            if not isinstance(workflows, list):
                raise AuditError("workflow response is invalid")
            self._workflows = workflows
        return self._workflows

    def check_branches(self) -> None:
        policy = self.policy()
        edges = [(branch.parent, branch.name) for branch in policy.values() if branch.parent]
        results = []
        for parent, child in edges:
            try:
                parent_doc = self.api.get(
                    f"repos/{self.config['repository']}/git/ref/heads/{quote(parent, safe='')}"
                )
                child_doc = self.api.get(
                    f"repos/{self.config['repository']}/git/ref/heads/{quote(child, safe='')}"
                )
                parent_sha = parent_doc["object"]["sha"]
                child_sha = child_doc["object"]["sha"]
                comparison = self.api.get(
                    f"repos/{self.config['repository']}/compare/{parent_sha}...{child_sha}"
                )
                behind = comparison.get("behind_by")
                status = comparison.get("status")
                valid = behind == 0 and status in ("ahead", "identical")
                results.append({
                    "parent": parent, "child": child, "status": status,
                    "ahead_by": comparison.get("ahead_by"), "behind_by": behind,
                    "valid": valid,
                })
                if not valid:
                    self.fail("branches", "BRANCH_DRIFT", f"{parent} -> {child}: {status}, child behind by {behind}")
            except PermissionUnknown:
                raise
            except (AuditError, KeyError, TypeError) as error:
                self.fail("branches", "BRANCH_API_ERROR", f"{parent} -> {child}: {error}")
        self.data["branches"] = {"valid_edges": sum(row["valid"] for row in results), "total_edges": len(edges), "edges": results}

    @staticmethod
    def labels(issue: dict[str, Any]) -> list[str]:
        return [item["name"] if isinstance(item, dict) else item for item in issue.get("labels", [])]

    @staticmethod
    def sections(body: str, heading: str) -> list[str]:
        pattern = re.compile(
            rf"(?ims)^##+\s+{re.escape(heading)}\s*$\n(.*?)(?=^##+\s+|\Z)"
        )
        return [match.strip() for match in pattern.findall(body or "")]

    def check_issues(self) -> None:
        issues = [item for item in self.all_issues() if "pull_request" not in item]
        open_issues = [item for item in issues if item.get("state") == "open"]
        counts = Counter()
        for issue in open_issues:
            names = self.labels(issue)
            workflows = [name for name in names if WORKFLOW_LABEL.match(name)]
            if len(workflows) > 1:
                self.fail("issues", "MULTIPLE_WORKFLOW_LABELS", f"issue #{issue['number']} has {len(workflows)} workflow labels")
            state = workflows[0] if len(workflows) == 1 else None
            if state:
                counts[state] += 1
            if state in ("workflow: ready", "workflow: active"):
                if "type: task" not in names:
                    self.fail("issues", "TASK_LABEL_MISSING", f"issue #{issue['number']} is {state} without type: task")
                sections = self.sections(issue.get("body") or "", "Next physical action")
                if len(sections) != 1 or not sections[0]:
                    self.fail("issues", "NEXT_ACTION_INVALID", f"issue #{issue['number']} must contain exactly one nonempty Next physical action section")
            if state == "workflow: blocked":
                body = issue.get("body") or ""
                blocker = self.sections(body, "Blocker") or re.findall(r"(?im)^\s*-?\s*Blocker:\s*(\S.*)$", body)
                unblock = self.sections(body, "Unblock condition") or re.findall(r"(?im)^\s*-?\s*Unblock condition:\s*(\S.*)$", body)
                if not blocker or not unblock or not blocker[0].strip() or not unblock[0].strip():
                    self.fail("issues", "BLOCKED_CONTRACT", f"issue #{issue['number']} lacks a blocker or unblock condition")
            if "system: reference" in names and workflows:
                self.fail("issues", "REFERENCE_HAS_WORKFLOW", f"issue #{issue['number']} is a reference with a workflow label")
        for label, limit in self.config["wip_limits"].items():
            if counts[label] > limit:
                self.fail("issues", "WIP_EXCEEDED", f"{label} WIP is {counts[label]}, limit {limit}")
        for issue in issues:
            names = self.labels(issue)
            if issue.get("state") == "closed" and "type: task" in names and any(WORKFLOW_LABEL.match(name) for name in names):
                self.fail("issues", "CLOSED_TASK_HAS_WORKFLOW", f"closed task issue #{issue['number']} retains a workflow label")

        number = self.config["reference_issue"]
        reference = next((item for item in issues if item.get("number") == number), None)
        if reference is None:
            self.fail("issues", "REFERENCE_MISSING", f"reference issue #{number} does not exist")
        else:
            if reference.get("state") != "open":
                self.fail("issues", "REFERENCE_CLOSED", f"reference issue #{number} is not open")
            if self.labels(reference) != ["system: reference"]:
                self.fail("issues", "REFERENCE_LABELS", f"reference issue #{number} must carry only system: reference")
            body = reference.get("body") or ""
            contract = (
                re.search(r"GitHub Issues are the only authoritative task source", body, re.I),
                re.search(r"Inbox\s*[→>-]+\s*Ready\s*[→>-]+\s*Active\s*[→>-]+\s*Closed", body, re.I),
                re.search(r"Blocked.*exception", body, re.I),
                re.search(r"(?:at most|max(?:imum)?)\s*3.*workflow:\s*active", body, re.I),
                re.search(r"(?:at most|max(?:imum)?)\s*3.*workflow:\s*ready", body, re.I),
            )
            if not all(contract):
                self.fail("issues", "REFERENCE_CONTRACT", f"reference issue #{number} does not describe the required task SSOT and WIP workflow")
            owner, repository = self.config["repository"].split("/", 1)
            if number not in self.api.pinned_issue_numbers(owner, repository):
                self.fail("issues", "REFERENCE_NOT_PINNED", f"reference issue #{number} is not pinned")
        self.data["issues"] = {"open_issue_count": len(open_issues), "workflow_counts": dict(sorted(counts.items())), "reference_issue": number}

    def check_labels(self) -> None:
        labels = {item["name"]: item for item in self.api.pages(f"repos/{self.config['repository']}/labels")}
        for name, expected in self.config["labels"].items():
            actual = labels.get(name)
            if actual is None:
                self.fail("labels", "LABEL_MISSING", f"required label {name!r} is missing")
                continue
            if actual.get("color", "").upper() != expected["color"].upper():
                self.fail("labels", "LABEL_COLOR", f"label {name!r} has unexpected color")
            if actual.get("description") != expected["description"]:
                self.fail("labels", "LABEL_DESCRIPTION", f"label {name!r} has unexpected description")
        self.data["labels"] = {"required": len(self.config["labels"]), "present": sum(name in labels for name in self.config["labels"])}

    def check_task_branches(self) -> None:
        refs = self.api.pages(f"repos/{self.config['repository']}/git/matching-refs/heads/task/")
        branches = [
            item["ref"].removeprefix("refs/heads/")
            for item in refs
            if item.get("ref", "").startswith("refs/heads/task/")
        ]
        issues = {item["number"]: item for item in self.all_issues() if "pull_request" not in item}
        prs = self.api.pages(f"repos/{self.config['repository']}/pulls?state=open")
        grouped: dict[int, list[str]] = defaultdict(list)
        valid = 0
        for branch in branches:
            match = TASK_BRANCH.fullmatch(branch)
            if not match:
                self.fail("task_branches", "TASK_BRANCH_FORMAT", f"task branch {branch!r} has invalid format")
                continue
            valid += 1
            number = int(match.group("issue"))
            grouped[number].append(branch)
            issue = issues.get(number)
            if issue is None:
                self.fail("task_branches", "TASK_ISSUE_MISSING", f"task branch {branch!r} references missing issue #{number}")
            else:
                if "type: task" not in self.labels(issue):
                    self.fail("task_branches", "TASK_TYPE_MISSING", f"task branch {branch!r} references an issue without type: task")
                if issue.get("state") == "closed":
                    self.fail("task_branches", "ORPHAN_TASK_BRANCH", f"task branch {branch!r} references closed issue #{number}")
        for number, names in grouped.items():
            if len(names) > 1:
                self.fail("task_branches", "DUPLICATE_TASK_BRANCH", f"issue #{number} has {len(names)} competing task branches")
        for pr in prs:
            head = pr.get("head", {}).get("ref", "")
            if not head.startswith("task/"):
                continue
            match = TASK_BRANCH.fullmatch(head)
            issue_number = int(match.group("issue")) if match else None
            task_issue = issues.get(issue_number) if issue_number else None
            base = pr.get("base", {}).get("ref", "")
            policy = self.policy()
            scope_target = next(
                (branch.name for branch in policy.values() if match and branch.scope == match.group("scope")),
                None,
            )
            if (
                not match
                or task_issue is None
                or "type: task" not in self.labels(task_issue)
                or base != scope_target
            ):
                self.fail("task_branches", "TASK_PR_MISMATCH", f"open PR #{pr.get('number')} does not map to a valid task issue")
        self.data["task_branches"] = {"count": len(branches), "valid_format": valid}

    def check_workflows(self) -> None:
        workflows = {item.get("name"): item for item in self.all_workflows()}
        for name in self.config["required_workflows"]:
            workflow = workflows.get(name)
            if workflow is None:
                self.fail("workflows", "WORKFLOW_MISSING", f"required workflow {name!r} is missing")
            elif workflow.get("state") != "active":
                self.fail("workflows", "WORKFLOW_DISABLED", f"required workflow {name!r} is {workflow.get('state')}")
        self.data["workflows"] = {"required": len(self.config["required_workflows"]), "active": sum(workflows.get(name, {}).get("state") == "active" for name in self.config["required_workflows"])}

    def _alerts(self, kind: str, endpoint: str) -> None:
        try:
            alerts = self.api.pages(endpoint)
        except PermissionUnknown as error:
            self.fail("security", "UNKNOWN_PERMISSION", f"{kind}: {error}; grant security-events: read")
            self.data["security"][kind] = {"status": "UNKNOWN_PERMISSION"}
            return
        except AuditError as error:
            if "HTTP 404" in str(error):
                self.fail("security", "UNKNOWN_PERMISSION", f"{kind}: read-only GitHub API permission unavailable (HTTP 404); grant security-events: read")
                self.data["security"][kind] = {"status": "UNKNOWN_PERMISSION"}
            else:
                self.fail("security", "SECURITY_API_ERROR", f"{kind}: {error}")
                self.data["security"][kind] = {"status": "ERROR"}
            return
        severity = Counter()
        scope = Counter()
        for alert in alerts:
            level = (alert.get("rule", {}).get("security_severity_level") if kind == "codeql" else alert.get("security_advisory", {}).get("severity")) or "unknown"
            severity[level.lower()] += 1
            if kind == "dependabot":
                scope[(alert.get("dependency", {}).get("scope") or "unknown").lower()] += 1
        self.data["security"][kind] = {"status": "KNOWN", "open": len(alerts), "by_severity": dict(sorted(severity.items()))}
        if scope:
            self.data["security"][kind]["by_scope"] = dict(sorted(scope.items()))
        if len(alerts) > self.config["security_thresholds"][kind]:
            self.fail("security", "SECURITY_ALERTS", f"{kind} has {len(alerts)} open alert(s)")

    def check_security(self) -> None:
        repository = self.config["repository"]
        self._alerts("codeql", f"repos/{repository}/code-scanning/alerts?state=open")
        self._alerts("dependabot", f"repos/{repository}/dependabot/alerts?state=open")
        self._alerts("secret_scanning", f"repos/{repository}/secret-scanning/alerts?state=open")
        by_name = {item.get("name"): item for item in self.all_workflows()}
        states = {}
        for name in self.config["security_workflows"]:
            workflow = by_name.get(name)
            if workflow is None:
                states[name] = "MISSING"
                self.fail("security", "SECURITY_WORKFLOW_MISSING", f"security workflow {name!r} is missing")
                continue
            try:
                document = self.api.get(f"repos/{repository}/actions/workflows/{workflow['id']}/runs?per_page=20")
            except (AuditError, PermissionUnknown) as error:
                states[name] = "ERROR"
                self.fail("security", "SECURITY_API_ERROR", f"security workflow {name!r}: {error}")
                continue
            runs = document.get("workflow_runs", []) if isinstance(document, dict) else []
            terminal = next((run for run in runs if run.get("status") == "completed"), None)
            if terminal is None:
                states[name] = "NO_TERMINAL_RUN"
                self.fail("security", "SECURITY_WORKFLOW_NO_RUN", f"security workflow {name!r} has no terminal run")
            else:
                states[name] = terminal.get("conclusion") or "UNKNOWN"
        self.data["security"]["workflow_conclusions"] = states

    def check_contracts(self) -> None:
        policy = self.policy()
        expected = {"main", "android-main", "apple-main", "linux-main", "windows-main", "android-phone", "android-vr", "android-vr-pico", "apple-ios"}
        if set(policy) != expected:
            self.fail("repository_contracts", "PERMANENT_BRANCH_SET", "branch policy must contain exactly the nine permanent branches")
        edges = [(branch.parent, branch.name) for branch in policy.values() if branch.parent]
        if len(edges) != 8 or len(edges) != len(set(edges)):
            self.fail("repository_contracts", "DUPLICATE_BRANCH_EDGE", "branch policy must define eight unique edges")
        for json_path in (self.root / ".github/branch-policy.json", self.root / ".github/repository-health.json"):
            try:
                load_json_strict(json_path)
            except (OSError, json.JSONDecodeError, AuditError) as error:
                self.fail("repository_contracts", "POLICY_JSON", f"{json_path.relative_to(self.root)} is invalid: {error}")
        for path in sorted((self.root / ".github/rulesets").glob("*.json")):
            try:
                load_json_strict(path)
            except (OSError, json.JSONDecodeError, AuditError) as error:
                self.fail("repository_contracts", "RULESET_JSON", f"{path.relative_to(self.root)} is invalid: {error}")
        workflows = sorted((self.root / ".github/workflows").glob("*.yml"))
        if yaml is None:
            self.fail("repository_contracts", "YAML_PARSER_MISSING", "PyYAML is required for fail-closed workflow syntax validation")
        for path in workflows:
            source = path.read_text(encoding="utf-8")
            if yaml is not None:
                try:
                    document = yaml.safe_load(source)
                    if not isinstance(document, dict):
                        raise ValueError("document is not a mapping")
                except (yaml.YAMLError, ValueError) as error:
                    self.fail("repository_contracts", "WORKFLOW_YAML", f"{path.relative_to(self.root)} is invalid YAML: {error}")
            if "\t" in source or not re.search(r"(?m)^name:\s*\S", source) or not re.search(r"(?m)^on:\s*(?:$|\S)", source) or not re.search(r"(?m)^jobs:\s*(?:$|\S)", source):
                self.fail("repository_contracts", "WORKFLOW_SYNTAX", f"{path.relative_to(self.root)} lacks the required YAML structure")
            for action in REMOTE_ACTION.findall(source):
                if action.startswith(("./", "docker://")):
                    continue
                if not FULL_PIN.fullmatch(action):
                    self.fail("repository_contracts", "ACTION_NOT_PINNED", f"{path.relative_to(self.root)} contains an action without a full commit pin")
        health_source = (self.root / ".github/workflows/repository-health.yml").read_text(encoding="utf-8")
        if re.search(r"(?m)^\s+[a-z-]+:\s*write\s*$", health_source):
            self.fail("repository_contracts", "WRITE_PERMISSION", "repository-health workflow contains a write permission")
        config_source = json.dumps(self.config, sort_keys=True)
        if SENSITIVE.search(config_source):
            self.fail("repository_contracts", "CONFIG_SECRET", "repository-health configuration resembles a secret")
        self.data["repository_contracts"] = {"permanent_branches": len(policy), "branch_edges": len(edges), "workflow_files": len(workflows)}


def redact(value: str) -> str:
    return SENSITIVE.sub("[REDACTED]", value)


def load_json_strict(path: Path) -> Any:
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result = {}
        for key, value in pairs:
            if key in result:
                raise AuditError(f"duplicate JSON key {key!r}")
            result[key] = value
        return result
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique)


def load_config(path: Path) -> dict[str, Any]:
    try:
        document = load_json_strict(path)
    except (OSError, json.JSONDecodeError, AuditError) as error:
        raise AuditError(f"cannot read repository-health configuration: {error}") from error
    required = {"schema", "repository", "reference_issue", "wip_limits", "labels", "required_workflows", "security_workflows", "security_thresholds"}
    if document.get("schema") != 1 or set(document) != required:
        raise AuditError("repository-health configuration does not match schema 1")
    expected_labels = {
        "workflow: inbox", "workflow: ready", "workflow: active", "workflow: blocked",
        "type: task", "system: reference",
    }
    if not isinstance(document["repository"], str) or re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", document["repository"]) is None:
        raise AuditError("repository-health repository name is invalid")
    if not isinstance(document["reference_issue"], int) or document["reference_issue"] < 1:
        raise AuditError("reference_issue must be a positive integer")
    if document["wip_limits"] != {"workflow: ready": 3, "workflow: active": 3}:
        raise AuditError("Ready and Active WIP limits must both be exactly 3")
    if not isinstance(document["labels"], dict) or set(document["labels"]) != expected_labels:
        raise AuditError("configuration must define exactly the six governance labels")
    for name, label in document["labels"].items():
        if not isinstance(label, dict) or set(label) != {"color", "description"} or re.fullmatch(r"[0-9A-Fa-f]{6}", label.get("color", "")) is None or not isinstance(label.get("description"), str) or not label["description"]:
            raise AuditError(f"label contract for {name!r} is invalid")
    for key in ("required_workflows", "security_workflows"):
        values = document[key]
        if not isinstance(values, list) or not values or len(values) != len(set(values)) or not all(isinstance(value, str) and value for value in values):
            raise AuditError(f"{key} must be a nonempty list of unique names")
    if set(document["security_thresholds"]) != {"codeql", "dependabot", "secret_scanning"} or any(value != 0 for value in document["security_thresholds"].values()):
        raise AuditError("all three security thresholds must be zero")
    return document


def summary(report: dict[str, Any]) -> str:
    lines = ["# Repository Health Doctor", "", f"Overall: **{report['status']}**", "", "| Area | Status | Findings |", "|---|---:|---:|"]
    for area, result in report["results"].items():
        lines.append(f"| {area.replace('_', ' ')} | {result['status']} | {len(result['findings'])} |")
    branches = report["results"]["branches"]["data"]
    if branches.get("edges"):
        lines.extend(["", "## Permanent branch hierarchy", ""])
        for edge in branches["edges"]:
            mark = "PASS" if edge["valid"] else "FAIL"
            lines.append(f"- {mark}: `{edge['parent']}` → `{edge['child']}` ({edge['status']}; ahead {edge['ahead_by']}, behind {edge['behind_by']})")
    findings = [(area, item) for area, result in report["results"].items() for item in result["findings"]]
    if findings:
        lines.extend(["", "## Findings", ""])
        lines.extend(f"- **{area} / {item['code']}**: {item['message']}" for area, item in findings)
    lines.extend(["", "The audit is read-only and performs no repair, merge, push, or Issue mutation."])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--local", action="store_true", help="validate versioned contracts only")
    args = parser.parse_args()
    try:
        config = load_config(args.config)
        doctor = Doctor(ROOT, config, None if args.local else GitHubApi(os.environ.get("GITHUB_TOKEN", "")))
        report = doctor.local() if args.local else doctor.live()
    except AuditError as error:
        report = {"schema": 1, "mode": "local" if args.local else "live", "repository": "UNKNOWN", "status": "FAIL", "exit_code": 2, "results": {area: {"status": "FAIL" if area == "repository_contracts" else "PASS", "findings": [{"code": "STARTUP_ERROR", "message": redact(str(error))}] if area == "repository_contracts" else [], "data": {}} for area in AREAS}}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    rendered = summary(report)
    print(rendered, end="")
    step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_summary:
        with open(step_summary, "a", encoding="utf-8") as stream:
            stream.write(rendered)
    return report["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
