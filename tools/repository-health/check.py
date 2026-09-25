#!/usr/bin/env python3
"""Fail-closed, read-only audit of Overte repository governance and security."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener, urlopen
import argparse
import importlib.util
import io
import json
import os
import re
import sys
import zipfile

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
OPERATIONAL_ERRORS = {"CHECK_ERROR", "STARTUP_ERROR", "UNKNOWN_PERMISSION", "SECURITY_API_ERROR", "BRANCH_API_ERROR"}
MAX_FRESHNESS_ARTIFACT_READS = 12
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

    def artifact_report(self, repository: str, artifact_id: int) -> dict[str, Any]:
        """Read one small JSON member; never extract or execute downloaded content."""
        class SafeRedirect(HTTPRedirectHandler):
            def redirect_request(self, request, response, code, message, headers, target):
                parsed = urlsplit(target)
                if parsed.scheme != 'https' or parsed.username or parsed.password:
                    raise AuditError('artifact redirect is not an HTTPS download')
                redirected = super().redirect_request(request, response, code, message, headers, target)
                # The archive is served through a signed URL, never forward the API token.
                redirected.remove_header('Authorization')
                return redirected

        request = Request(
            f'https://api.github.com/repos/{repository}/actions/artifacts/{artifact_id}/zip',
            headers={'Authorization': f'Bearer {self.token}',
                     'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28'})
        try:
            with build_opener(SafeRedirect()).open(request, timeout=30) as response:
                archive = response.read(2_000_001)
            if len(archive) > 2_000_000:
                raise AuditError('health artifact exceeds the download size limit')
            with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
                members = bundle.infolist()
                if (len(members) != 1 or members[0].filename != 'repository-health-report.json'
                        or members[0].file_size > 1_000_000 or members[0].flag_bits & 1):
                    raise AuditError('health artifact must contain only one bounded JSON report')
                document = json.loads(bundle.read(members[0]))
            if not isinstance(document, dict):
                raise AuditError('health report is not an object')
            return document
        except (HTTPError, URLError, TimeoutError, zipfile.BadZipFile, json.JSONDecodeError,
                RuntimeError, UnicodeDecodeError) as error:
            raise AuditError(f'cannot read health artifact ({type(error).__name__})') from error

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
        self.executed: set[str] = set()
        self._issues: list[dict[str, Any]] | None = None
        self._workflows: list[dict[str, Any]] | None = None

    def fail(self, area: str, code: str, message: str) -> None:
        self.findings[area].append(Finding(code, redact(message)))

    def _guard(self, area: str, function: Any) -> None:
        self.executed.add(area)
        try:
            function()
        except PermissionUnknown as error:
            self.fail(area, "UNKNOWN_PERMISSION", str(error))
        except (AuditError, OSError, ValueError, AttributeError, KeyError, TypeError) as error:
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

    def propagation_state(self, now: datetime) -> dict[str, Any]:
        """Read-only admission, not a successful repository-health result."""
        policy = self.policy()
        repository = self.config['repository']
        prefix = f"repos/{repository}"

        def age(value: Any) -> float:
            if not isinstance(value, str):
                raise AuditError("propagation timestamp missing")
            moment = datetime.fromisoformat(value.replace('Z', '+00:00'))
            if moment.tzinfo is None:
                raise AuditError("propagation timestamp has no timezone")
            elapsed = (now - moment).total_seconds()
            if elapsed < -300:
                raise AuditError("propagation timestamp is in the future")
            return max(0, elapsed)

        heads = {}
        recent = False
        for name in policy:
            ref = self.api.get(f"{prefix}/git/ref/heads/{quote(name, safe='')}")
            sha = ref['object']['sha']
            if not isinstance(sha, str) or not re.fullmatch('[0-9a-f]{40}', sha):
                raise AuditError("invalid permanent head during admission")
            heads[name] = sha
            commit = self.api.get(f"{prefix}/commits/{sha}")
            if commit['sha'] != sha:
                raise AuditError("commit identity changed during admission")
            recent |= age(commit['commit']['committer']['date']) < 1800

        reasons = []
        for pr in self.api.pages(f"{prefix}/pulls?state=open"):
            base, head = pr['base'], pr['head']
            target = policy.get(base['ref'])
            if (target is None or target.parent is None or
                    base['repo']['full_name'] != repository or
                    not head.get('repo') or head['repo']['full_name'] != repository):
                continue
            reconciliation = re.fullmatch(
                rf"reconcile/{re.escape(target.scope)}/[a-z0-9]+(?:-[a-z0-9]+)*", head['ref'])
            if head['ref'] == target.parent or reconciliation:
                if age(pr['created_at']) > 7200:
                    raise AuditError("propagation PR exceeds two-hour admission lease; inspect it")
                reasons.append('OPEN_PROPAGATION_PR')

        for status in ('queued', 'in_progress', 'waiting', 'pending', 'requested'):
            document = self.api.get(
                f"{prefix}/actions/workflows/parent-qualification.yml/runs?status={status}&per_page=100")
            if not isinstance(document, dict):
                raise AuditError("qualification activity response is not an object")
            runs, count = document.get('workflow_runs'), document.get('total_count')
            if (not isinstance(runs, list) or type(count) is not int or
                    count != len(runs) or count > 100):
                raise AuditError("qualification activity response incomplete")
            for run in runs:
                if run['status'] != status:
                    raise AuditError("qualification activity status mismatch")
                branch = policy.get(run['head_branch'])
                if branch is not None and branch.children:
                    if age(run['created_at']) > 7200:
                        raise AuditError("qualification exceeds two-hour admission lease; inspect it")
                    reasons.append('PARENT_QUALIFICATION_ACTIVE')

        synchronized = True
        for branch in policy.values():
            if branch.parent:
                comparison = self.api.get(
                    f"{prefix}/compare/{heads[branch.parent]}...{heads[branch.name]}")
                behind, status = comparison.get('behind_by'), comparison.get('status')
                if type(behind) is not int or behind < 0 or status not in ('ahead', 'behind', 'diverged', 'identical'):
                    raise AuditError("invalid hierarchy response during admission")
                synchronized &= behind == 0 and status in ('ahead', 'identical')
        # Bridges the gap between a parent merge and the next PR/qualification.
        # An abandoned drift is NOT hidden indefinitely: after30min it is audited.
        if recent and not synchronized:
            reasons.append('RECENT_UNFINISHED_PROPAGATION')
        return {'status': 'DEFERRED_PROPAGATION' if reasons else 'READY',
                'heads': heads, 'reasons': sorted(set(reasons)),
                'hierarchy_synchronized': synchronized}

    def live_when_idle(self, event: str, clock: Any = None) -> dict[str, Any]:
        clock = clock or (lambda: datetime.now(timezone.utc))
        now = clock()
        before = self.propagation_state(now)
        if before['status'] != 'READY':
            report = self.report('live')
            report.update(status=before['status'], exit_code=0, admission=before, generated_at=timestamp(now))
            return report
        source_sha = os.environ.get('HEALTH_SOURCE_SHA')
        if source_sha and before['heads']['main'] != source_sha:
            report = self.report('live')
            report.update(status='DEFERRED_SOURCE_CHANGED', exit_code=0,
                          admission={'accepted': False, 'before': before}, generated_at=timestamp(now))
            return report
        report = self.live()
        report.update(audit_executed=True, audit_started_at=timestamp(now))
        try:
            after = self.propagation_state(clock())
        except (AuditError, AttributeError, KeyError, TypeError, ValueError) as error:
            report.update(status='FAIL', exit_code=2,
                          admission={'accepted': False, 'error': redact(str(error)), 'before': before})
            return report
        report['admission'] = {'before': before, 'after': after}
        if after['status'] != 'READY' or before['heads'] != after['heads']:
            # A changing repository withdraws the proof, never an independent failure.
            report['admission']['accepted'] = False
            if all(not result['findings'] for area, result in report['results'].items() if area != 'branches'):
                report.update(status='DEFERRED_REPOSITORY_CHANGED', exit_code=0)
        else:
            report['admission']['accepted'] = True
            report['audit_complete'] = (
                all(result['status'] in ('PASS', 'FAIL') for result in report['results'].values())
                and report['exit_code'] != 2)
            if report['audit_complete']:
                # A complete failed audit is fresh evidence, not a healthy repository.
                report['audit_completed_at'] = timestamp(clock())
        report['generated_at'] = timestamp(clock())
        return report

    def report(self, mode: str) -> dict[str, Any]:
        results = {}
        for area in AREAS:
            results[area] = {
                "status": "FAIL" if self.findings[area] else ("PASS" if area in self.executed else "NOT_RUN"),
                "findings": [asdict(item) for item in self.findings[area]],
                "data": self.data[area],
            }
        has_operational_error = any(
            finding.code in OPERATIONAL_ERRORS
            for findings in self.findings.values() for finding in findings)
        status = "FAIL" if any(self.findings.values()) else "PASS"
        return {
            "schema": 2, "mode": mode, "repository": self.config["repository"],
            "status": status,
            "exit_code": 0 if status == "PASS" else (2 if has_operational_error else 1),
            "generated_at": timestamp(), "audit_executed": False, "audit_complete": False,
            "audit_started_at": None, "audit_completed_at": None,
            "source_sha": os.environ.get('HEALTH_SOURCE_SHA'),
            "run_id": os.environ.get('GITHUB_RUN_ID'),
            "run_attempt": os.environ.get('GITHUB_RUN_ATTEMPT'),
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
            collected = []
            for page in range(1, 11):
                document = self.api.get(
                    f"repos/{self.config['repository']}/actions/workflows?per_page=100&page={page}")
                workflows = document.get("workflows") if isinstance(document, dict) else None
                count = document.get('total_count') if isinstance(document, dict) else None
                if not isinstance(workflows, list) or type(count) is not int or count < 0:
                    raise AuditError("workflow response is invalid")
                collected.extend(workflows)
                if len(collected) == count:
                    self._workflows = collected
                    break
                if not workflows or len(collected) > count:
                    raise AuditError("workflow response is incomplete or changed during pagination")
            if self._workflows is None:
                raise AuditError("workflow inventory exceeds 1000 entries")
            paths = [item.get('path') for item in self._workflows]
            if not all(isinstance(path, str) for path in paths) or len(paths) != len(set(paths)):
                raise AuditError("workflow inventory has missing or duplicate paths")
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
        # Intake owns the archive format and hash verification. Workflow checks
        # must inspect the current body without treating preserved history as work.
        spec = importlib.util.spec_from_file_location("overte_issue_intake", self.root / "tools/issue-intake/intake.py")
        if not spec or not spec.loader:
            raise AuditError("cannot load the issue-intake validator")
        intake = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(intake)
        policy = intake.load_policy(path=self.root / ".github/issue-policy.json")
        issues = [item for item in self.all_issues() if "pull_request" not in item]
        current_bodies = {}
        for issue in issues:
            try:
                current, archive = intake.extract_archive(issue.get('body') or '')
                if archive is not None and archive.get('issue') != issue['number']:
                    raise intake.IntakeError('Original-description archive belongs to a different issue')
                current_bodies[issue['number']] = current
            except (intake.IntakeError, ValueError, TypeError, AttributeError) as error:
                self.fail('issues', 'ISSUE_ARCHIVE_INVALID', f"issue #{issue['number']}: {error}")
                current_bodies[issue['number']] = None
        open_issues = [item for item in issues if item.get("state") == "open"]
        counts = Counter()
        for issue in open_issues:
            names = self.labels(issue)
            workflows = [name for name in names if WORKFLOW_LABEL.match(name)]
            if len(workflows) > 1:
                self.fail("issues", "MULTIPLE_WORKFLOW_LABELS", f"issue #{issue['number']} has {len(workflows)} workflow labels")
            state = workflows[0] if len(workflows) == 1 else None
            body = current_bodies[issue['number']]
            if state:
                counts[state] += 1
            if state in ("workflow: ready", "workflow: active"):
                if not {"type: task", "bug", "acceptance"}.intersection(names):
                    self.fail("issues", "TASK_LABEL_MISSING", f"issue #{issue['number']} is {state} without a concrete work type")
                sections = self.sections(body or '', "Next physical action") + self.sections(body or '', "Next action")
                if body is not None and (len(sections) != 1 or not sections[0]):
                    self.fail("issues", "NEXT_ACTION_INVALID", f"issue #{issue['number']} must contain exactly one nonempty Next physical action section")
            if state == "workflow: blocked" and body is not None:
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
            body = current_bodies[reference['number']] or ''
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
        # The same validator handles structured intake; legacy issues remain visible
        # as migration work without silently redefining their historical contract.
        structured = [intake.inspect_issue(item, policy) for item in issues]
        for item in structured:
            for error in item["errors"]:
                self.fail("issues", "ISSUE_STRUCTURE", f"issue #{item['number']}: {error}")
        self.data["issues"]["legacy_issue_count"] = sum(item["status"] == "legacy" for item in structured)
        self.data["issues"]["structured_issue_count"] = sum(item["status"] in ("valid", "invalid") for item in structured)

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
        workflows = {item['path']: item for item in self.all_workflows()}
        heads = {}
        for expected in self.config['required_workflows']:
            path, owner = expected['path'], expected['owner_branch']
            workflow = workflows.get(path)
            if workflow is None:
                self.fail('workflows', 'WORKFLOW_MISSING', f'required workflow {path!r} is missing')
            elif workflow.get('state') != 'active':
                self.fail('workflows', 'WORKFLOW_DISABLED', f'required workflow {path!r} is {workflow.get("state")}')
            if owner:
                if owner not in heads:
                    ref = self.api.get(f"repos/{self.config['repository']}/git/ref/heads/{quote(owner, safe='')}")
                    heads[owner] = ref['object']['sha']
                    if not isinstance(heads[owner], str) or not re.fullmatch('[0-9a-f]{40}', heads[owner]):
                        raise AuditError('workflow owner head is invalid')
                try:
                    source = self.api.get(
                        f"repos/{self.config['repository']}/contents/{path}?ref={heads[owner]}")
                    if not isinstance(source, dict) or source.get('type') != 'file' or source.get('path') != path:
                        raise AuditError('workflow source is not the expected file')
                except AuditError as error:
                    if 'HTTP 404' not in str(error):
                        raise
                    self.fail('workflows', 'WORKFLOW_SOURCE_MISSING', f'{path!r} is missing from owning branch {owner!r}')
        self.data['workflows'] = {
            'required': len(self.config['required_workflows']),
            'active': sum(workflows.get(item['path'], {}).get('state') == 'active'
                          for item in self.config['required_workflows']),
            'owner_heads': heads,
        }

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
        by_name = {item.get("path"): item for item in self.all_workflows()}
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
        expected = {"main", "android-main", "apple-main", "android-phone", "android-vr", "android-vr-pico", "apple-ios"}
        if set(policy) != expected:
            self.fail("repository_contracts", "PERMANENT_BRANCH_SET", "branch policy must contain exactly the seven permanent branches")
        edges = [(branch.parent, branch.name) for branch in policy.values() if branch.parent]
        if len(edges) != 6 or len(edges) != len(set(edges)):
            self.fail("repository_contracts", "DUPLICATE_BRANCH_EDGE", "branch policy must define six unique edges")
        for json_path in (self.root / ".github/branch-policy.json", self.root / ".github/repository-health.json"):
            try:
                load_json_strict(json_path)
            except (OSError, json.JSONDecodeError, AuditError) as error:
                self.fail("repository_contracts", "POLICY_JSON", f"{json_path.relative_to(self.root)} is invalid: {error}")
        for entry in self.config['required_workflows']:
            if entry['owner_branch'] == 'main' and not (self.root / entry['path']).is_file():
                self.fail('repository_contracts', 'WORKFLOW_SOURCE_MISSING',
                          f"main-owned workflow {entry['path']!r} is missing")
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


def timestamp(moment: datetime | None = None) -> str:
    return (moment or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')


def moment(value: Any) -> datetime:
    if not isinstance(value, str):
        raise AuditError('missing audit timestamp')
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as error:
        raise AuditError('invalid audit timestamp') from error
    if parsed.tzinfo is None:
        raise AuditError('audit timestamp has no timezone')
    return parsed


def validate_audit_evidence(report: dict[str, Any], run: dict[str, Any],
                            config: dict[str, Any], now: datetime) -> bool:
    """Validate provenance even for a deferred report; completeness is separate."""
    if not isinstance(report, dict) or not isinstance(run, dict):
        raise AuditError('health evidence is not an object')
    if (report.get('schema') != 2 or report.get('repository') != config['repository']
            or report.get('mode') != 'live' or report.get('source_sha') != run['head_sha']
            or str(report.get('run_id')) != str(run['id'])
            or str(report.get('run_attempt')) != str(run['run_attempt'])):
        raise AuditError('health report identity does not match its trusted workflow run')
    generated = moment(report.get('generated_at'))
    if generated > now or generated < moment(run['created_at']):
        raise AuditError('health report timestamp is outside its workflow run')
    if run.get('status') == 'completed' and generated > moment(run.get('updated_at')):
        raise AuditError('health report was generated after its workflow completed')
    if report.get('audit_complete') is not True:
        return False
    areas = report.get('results')
    admission = report.get('admission', {})
    before = admission.get('before', {}).get('heads')
    after = admission.get('after', {}).get('heads')
    if (report.get('audit_executed') is not True or report.get('status') not in ('PASS', 'FAIL')
            or report.get('exit_code') != (0 if report['status'] == 'PASS' else 1)
            or not isinstance(areas, dict) or set(areas) != set(AREAS)
            or any(not isinstance(result, dict) or result.get('status') not in ('PASS', 'FAIL')
                   for result in areas.values())
            or admission.get('accepted') is not True or not isinstance(before, dict)
            or set(before) != {'main', 'android-main', 'android-phone', 'android-vr', 'android-vr-pico', 'apple-main', 'apple-ios'}
            or before != after or before.get('main') != run['head_sha']
            or not all(isinstance(sha, str) and re.fullmatch('[0-9a-f]{40}', sha) for sha in before.values())):
        raise AuditError('complete health report lacks a stable, fully executed audit')
    for result in areas.values():
        findings = result.get('findings')
        if (not isinstance(findings, list)
                or any(not isinstance(finding, dict) or not isinstance(finding.get('code'), str)
                       or finding['code'] in OPERATIONAL_ERRORS for finding in findings)
                or (result['status'] == 'PASS' and findings)):
            raise AuditError('complete health report contains unknown or inconsistent findings')
    if (report['status'] == 'PASS') != all(result['status'] == 'PASS' for result in areas.values()):
        raise AuditError('health result disagrees with area results')
    started, completed = moment(report.get('audit_started_at')), moment(report.get('audit_completed_at'))
    if not moment(run['created_at']) <= started <= completed <= generated:
        raise AuditError('audit completion timestamp is invalid')
    return True


def freshness(config: dict[str, Any], api: Any, now: datetime | None = None) -> dict[str, Any]:
    """Inspect authenticated run artifacts, including complete audits with findings."""
    now = now or datetime.now(timezone.utc)
    result = {'schema': 2, 'mode': 'freshness', 'repository': config['repository'],
              'generated_at': timestamp(now), 'status': 'MISSING', 'exit_code': 1,
              'max_age_hours': config['freshness']['max_age_hours'],
              'last_complete_at': None, 'last_complete_status': None, 'source_run_id': None,
              'source_sha': None, 'last_attempt_status': None, 'reports_checked': 0,
              'artifact_inventories_read': 0,
              'evidence_verification': 'authenticated_github_artifact', 'findings': []}
    prefix = f"repos/{config['repository']}"
    try:
        repository = api.get(prefix)
        if repository.get('full_name') != config['repository'] or repository.get('default_branch') != 'main':
            raise AuditError('freshness requires the configured fork and its trusted main branch')
        workflow = api.get(f"{prefix}/actions/workflows/repository-health.yml")
        path = config['freshness']['workflow_path']
        if workflow.get('path') != path or workflow.get('state') != 'active' or type(workflow.get('id')) is not int:
            raise AuditError('trusted health workflow is missing or inactive')
        document = api.get(f"{prefix}/actions/workflows/{workflow['id']}/runs?branch=main&per_page=100")
        runs = document.get('workflow_runs') if isinstance(document, dict) else None
        if (not isinstance(runs, list) or type(document.get('total_count')) is not int
                or document['total_count'] < len(runs) or len(runs) > 100
                or any(not isinstance(run, dict) for run in runs)):
            raise AuditError('health run inventory is invalid')
        eligible = []
        # A terminal run's API update time bounds its report completion. Nonterminal
        # runs may already have uploaded a report, so their upper bound is now.
        for run in runs:
            if run.get('event') not in ('schedule', 'workflow_dispatch'):
                continue
            if (run.get('repository', {}).get('full_name') != config['repository']
                    or run.get('head_repository', {}).get('full_name') != config['repository']
                    or run.get('head_branch') != 'main' or run.get('path') != path
                    or run.get('workflow_id') != workflow['id']
                    or type(run.get('id')) is not int or type(run.get('run_attempt')) is not int
                    or not isinstance(run.get('head_sha'), str)
                    or not re.fullmatch('[0-9a-f]{40}', run['head_sha'])):
                raise AuditError('health run does not match trusted repository/workflow identity')
            created, updated = moment(run.get('created_at')), moment(run.get('updated_at'))
            if not created <= updated <= now:
                raise AuditError('health run timestamps are invalid')
            if run.get('status') not in ('completed', 'queued', 'in_progress', 'waiting', 'pending', 'requested'):
                raise AuditError('health run status is invalid')
            eligible.append((updated if run['status'] == 'completed' else now, run))
        eligible.sort(key=lambda item: item[0], reverse=True)
        complete = []
        for upper_bound, run in eligible:
            if complete and max(moment(item['audit_completed_at']) for item in complete) > upper_bound:
                # Every remaining candidate must be older; do not download history.
                break
            if result['artifact_inventories_read'] >= MAX_FRESHNESS_ARTIFACT_READS:
                raise AuditError('health evidence query budget exhausted before the newest complete audit was established')
            result['artifact_inventories_read'] += 1
            artifacts = api.get(f"{prefix}/actions/runs/{run['id']}/artifacts?per_page=100")
            rows = artifacts.get('artifacts') if isinstance(artifacts, dict) else None
            if (not isinstance(rows, list) or artifacts.get('total_count') != len(rows)
                    or any(not isinstance(row, dict) for row in rows)):
                raise AuditError('health artifact inventory is incomplete')
            name = f"{config['freshness']['artifact_prefix']}-{run['id']}-{run['run_attempt']}"
            candidates = [item for item in rows if item.get('name') == name and item.get('expired') is False]
            if len(candidates) > 1:
                raise AuditError('health report artifact is ambiguous')
            if not candidates:
                if result['last_attempt_status'] is None:
                    result['last_attempt_status'] = 'MISSING_ARTIFACT'
                continue
            artifact = candidates[0]
            if (type(artifact.get('id')) is not int or artifact.get('workflow_run', {}).get('id') != run['id']
                    or artifact['workflow_run'].get('head_sha') != run['head_sha']):
                raise AuditError('health artifact does not belong to its workflow run')
            report = api.artifact_report(config['repository'], artifact['id'])
            is_complete = validate_audit_evidence(report, run, config, now)
            result['reports_checked'] += 1
            if result['last_attempt_status'] is None:
                result['last_attempt_status'] = report['status']
            if is_complete:
                complete.append(report)
        if complete:
            latest = max(complete, key=lambda item: moment(item['audit_completed_at']))
            age = (now - moment(latest['audit_completed_at'])).total_seconds() / 3600
            result.update(last_complete_at=latest['audit_completed_at'], last_complete_status=latest['status'],
                          source_run_id=latest['run_id'], source_sha=latest['source_sha'], age_hours=round(age, 3),
                          status='FRESH' if age <= result['max_age_hours'] else 'STALE')
            result['exit_code'] = 0 if result['status'] == 'FRESH' else 1
    except (AuditError, AttributeError, KeyError, TypeError, ValueError) as error:
        result.update(status='UNKNOWN', exit_code=2)
        result['findings'].append({'code': 'FRESHNESS_EVIDENCE_ERROR', 'message': redact(str(error))})
    return result


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
    required = {"schema", "repository", "reference_issue", "wip_limits", "labels", "required_workflows", "security_workflows", "security_thresholds", "freshness"}
    if document.get("schema") != 2 or set(document) != required:
        raise AuditError("repository-health configuration does not match schema 2")
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
    inventory = document['required_workflows']
    if not isinstance(inventory, list) or not inventory:
        raise AuditError('required_workflows must be a nonempty path inventory')
    paths = []
    owners = {'main', 'android-main', 'android-phone', 'android-vr', 'android-vr-pico', 'apple-main', 'apple-ios'}
    for entry in inventory:
        if not isinstance(entry, dict) or set(entry) != {'path', 'owner_branch'}:
            raise AuditError('invalid workflow inventory entry')
        path, owner = entry['path'], entry['owner_branch']
        if not isinstance(path, str) or not (
            (re.fullmatch(r'\.github/workflows/[a-z0-9-]+\.yml', path) and owner in owners)
            or (path in {'dynamic/dependabot/dependabot-updates', 'dynamic/dependabot/update-graph'} and owner is None)):
            raise AuditError('workflow path or owning branch is invalid')
        paths.append(path)
    if len(paths) != len(set(paths)):
        raise AuditError('workflow inventory paths must be unique')
    security = document['security_workflows']
    if not isinstance(security, list) or not security or not all(isinstance(path, str) and path in paths for path in security) or len(security) != len(set(security)):
        raise AuditError('security_workflows must contain unique registered paths')
    freshness = document['freshness']
    if (not isinstance(freshness, dict) or set(freshness) != {'max_age_hours', 'workflow_path', 'artifact_prefix'}
            or type(freshness['max_age_hours']) is not int or not 6 <= freshness['max_age_hours'] <= 168
            or freshness['workflow_path'] != '.github/workflows/repository-health.yml'
            or freshness['artifact_prefix'] != 'repository-health-report'):
        raise AuditError('invalid freshness policy')
    if set(document["security_thresholds"]) != {"codeql", "dependabot", "secret_scanning"} or any(value != 0 for value in document["security_thresholds"].values()):
        raise AuditError("all three security thresholds must be zero")
    return document


def summary(report: dict[str, Any]) -> str:
    if report['mode'] == 'freshness':
        return (f"# Repository Health Freshness\n\nEvidence: **{report['status']}**\n\n"
                f"Last complete audit: {report['last_complete_at'] or 'none'}; "
                f"result: {report['last_complete_status'] or 'unknown'}.\n\n"
                "Freshness records execution, not repository health.\n")
    lines = ["# Repository Health Doctor", "", f"Overall: **{report['status']}** ({report['mode']})",
             f"Full audit complete: **{report.get('audit_complete', False)}**; completed at: {report.get('audit_completed_at') or 'none'}.",
             "", "| Area | Status | Findings |", "|---|---:|---:|"]
    for area, result in report["results"].items():
        lines.append(f"| {area.replace('_', ' ')} | {result['status']} | {len(result['findings'])} |")
    branches = report["results"]["branches"]["data"]
    if branches.get("edges"):
        lines.extend(["", "## Permanent branch hierarchy", ""])
        for edge in branches["edges"]:
            mark = "PASS" if edge["valid"] else "FAIL"
            lines.append(f"- {mark}: `{edge['parent']}` → `{edge['child']}` ({edge['status']}; ahead {edge['ahead_by']}, behind {edge['behind_by']})")
    workflow_conclusions = report['results']['security']['data'].get('workflow_conclusions', {})
    if workflow_conclusions:
        lines.extend(['', '## Security workflow observations', '',
                      'Latest observed terminal run (not necessarily main). Candidate failures remain visible observations; '
                      'they do not establish a failure of the current default branch.', '',
                      '| Workflow path | Latest observed conclusion |', '| --- | --- |'])
        for path, conclusion in sorted(workflow_conclusions.items()):
            lines.append(f'| `{path}` | **{conclusion}** |')
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
    parser.add_argument("--freshness", action="store_true", help="verify recent full live audits from trusted GitHub artifacts")
    parser.add_argument("--local", action="store_true", help="validate versioned contracts only")
    parser.add_argument("--when-idle", action="store_true", help="explicit alias for default live propagation admission")
    parser.add_argument("--event", choices=('schedule', 'workflow_dispatch'), default='workflow_dispatch')
    args = parser.parse_args()
    try:
        config = load_config(args.config)
        if args.local and args.freshness:
            raise AuditError("freshness requires authenticated live evidence, not local contract checks")
        doctor = Doctor(ROOT, config, None if args.local else GitHubApi(os.environ.get("GITHUB_TOKEN", "")))
        if args.local and args.when_idle:
            raise AuditError("local tests cannot claim live quiescence")
        # Legacy direct CLI invocations must not bypass the new live admission.
        report = freshness(config, doctor.api) if args.freshness else (doctor.local() if args.local else doctor.live_when_idle(args.event))
    except (AuditError, AttributeError, KeyError, TypeError, ValueError) as error:
        report = {"schema": 2, "generated_at": timestamp(), "audit_executed": False, "audit_complete": False, "audit_started_at": None, "audit_completed_at": None, "mode": "local" if args.local else "live", "repository": "UNKNOWN", "status": "FAIL", "exit_code": 2, "results": {area: {"status": "FAIL" if area == "repository_contracts" else "NOT_RUN", "findings": [{"code": "STARTUP_ERROR", "message": redact(str(error))}] if area == "repository_contracts" else [], "data": {}} for area in AREAS}}
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
