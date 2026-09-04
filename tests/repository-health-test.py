#!/usr/bin/env python3
"""Fixture and workflow-contract tests for the Repository Health Doctor."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import importlib.util
import json
import os
import re
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "tools/repository-health/check.py"
SPEC = importlib.util.spec_from_file_location("repository_health", CHECKER)
assert SPEC and SPEC.loader
HEALTH = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = HEALTH
SPEC.loader.exec_module(HEALTH)
CONFIG = HEALTH.load_config(ROOT / ".github/repository-health.json")
SHA = "1" * 40


REFERENCE_BODY = """GitHub Issues are the only authoritative task source (task SSOT).

Inbox → Ready → Active → Closed; Blocked is an exception state.
At most 3 repository-wide `workflow: active` Issues.
At most 3 repository-wide `workflow: ready` Issues.
"""


def issue(number, *, state="open", labels=(), body="", pull=False):
    value = {
        "number": number,
        "state": state,
        "labels": [{"name": name} for name in labels],
        "body": body,
        "title": f"Issue {number}",
    }
    if pull:
        value["pull_request"] = {}
    return value


def reference(**changes):
    value = issue(599, labels=("system: reference",), body=REFERENCE_BODY)
    value.update(changes)
    return value


class FakeApi:
    def __init__(self):
        self.issues = [reference()]
        self.labels = [
            {"name": name, "color": expected["color"], "description": expected["description"]}
            for name, expected in CONFIG["labels"].items()
        ]
        self.refs = []
        self.prs = []
        self.workflows = [
            {"id": index + 1, "name": name, "state": "active"}
            for index, name in enumerate(CONFIG["required_workflows"])
        ]
        self.alerts = {"code-scanning": [], "dependabot": [], "secret-scanning": []}
        self.pinned = {599}
        self.comparisons = {}
        self.fail_contains = {}

    def _failure(self, path):
        for needle, error in self.fail_contains.items():
            if needle in path:
                raise error

    def get(self, path):
        self._failure(path)
        if "/git/ref/heads/" in path:
            return {"object": {"sha": SHA}}
        if "/compare/" in path:
            child = path.rsplit("...", 1)[-1]
            return self.comparisons.get(child, {"status": "identical", "ahead_by": 0, "behind_by": 0})
        if path.endswith("/actions/workflows?per_page=100"):
            return {"workflows": self.workflows}
        if "/actions/workflows/" in path and "/runs?" in path:
            return {"workflow_runs": [{"status": "completed", "conclusion": "success"}]}
        raise AssertionError(f"unexpected GET {path}")

    def pages(self, path, limit=100):
        self._failure(path)
        if "/issues?" in path:
            return self.issues
        if path.endswith("/labels"):
            return self.labels
        if "/git/matching-refs/heads/task/" in path:
            return self.refs
        if "/pulls?" in path:
            return self.prs
        for key, alerts in self.alerts.items():
            if f"/{key}/alerts?" in path:
                return alerts
        raise AssertionError(f"unexpected pages {path}")

    def pinned_issue_numbers(self, owner, repository):
        return self.pinned


def doctor(api=None):
    return HEALTH.Doctor(ROOT, deepcopy(CONFIG), api or FakeApi())


class BranchFixtures(unittest.TestCase):
    def test_all_eight_edges_are_valid(self):
        subject = doctor()
        subject.check_branches()
        self.assertEqual(subject.data["branches"]["valid_edges"], 8)
        self.assertEqual(subject.findings["branches"], [])

    def test_missing_branch_and_api_error_fail_without_stopping_other_edges(self):
        api = FakeApi()
        api.fail_contains["android-phone"] = HEALTH.AuditError("simulated API failure")
        subject = doctor(api)
        subject.check_branches()
        self.assertEqual(len(subject.data["branches"]["edges"]), 7)
        self.assertEqual(subject.findings["branches"][0].code, "BRANCH_API_ERROR")

    def test_behind_and_diverged_edges_fail(self):
        for comparison in (
            {"status": "behind", "ahead_by": 0, "behind_by": 1},
            {"status": "diverged", "ahead_by": 2, "behind_by": 1},
        ):
            with self.subTest(comparison=comparison):
                api = FakeApi()
                api.comparisons[SHA] = comparison
                subject = doctor(api)
                subject.check_branches()
                self.assertTrue(subject.findings["branches"])

    def test_historical_refs_are_not_branch_edges(self):
        subject = doctor()
        subject.check_branches()
        names = {edge["child"] for edge in subject.data["branches"]["edges"]}
        self.assertNotIn("reconcile/main/S1-B04", names)


class IssueFixtures(unittest.TestCase):
    def run_issues(self, values, *, pinned=True):
        api = FakeApi()
        api.issues = values
        api.pinned = {599} if pinned else set()
        subject = doctor(api)
        subject.check_issues()
        return subject

    def test_valid_empty_queue_and_reference(self):
        self.assertEqual(self.run_issues([reference()]).findings["issues"], [])

    def test_active_three_passes_but_active_four_and_ready_four_fail(self):
        action = "## Next physical action\nRun the next check.\n"
        for label, count, expected in (("workflow: active", 3, False), ("workflow: active", 4, True), ("workflow: ready", 4, True)):
            with self.subTest(label=label, count=count):
                values = [reference()] + [issue(n, labels=(label, "type: task"), body=action) for n in range(1, count + 1)]
                codes = {finding.code for finding in self.run_issues(values).findings["issues"]}
                self.assertEqual("WIP_EXCEEDED" in codes, expected)

    def test_multiple_workflow_labels_and_missing_type_fail(self):
        values = [reference(), issue(1, labels=("workflow: ready", "workflow: active"), body="## Next physical action\nDo it")]
        codes = {item.code for item in self.run_issues(values).findings["issues"]}
        self.assertIn("MULTIPLE_WORKFLOW_LABELS", codes)

    def test_missing_or_multiple_next_action_fails(self):
        bodies = ("", "## Next physical action\nOne\n## Next physical action\nTwo\n")
        for body in bodies:
            with self.subTest(body=body):
                values = [reference(), issue(1, labels=("workflow: active", "type: task"), body=body)]
                codes = {item.code for item in self.run_issues(values).findings["issues"]}
                self.assertIn("NEXT_ACTION_INVALID", codes)

    def test_valid_blocked_issue_and_missing_unblock_condition(self):
        valid = issue(1, labels=("workflow: blocked", "type: task"), body="## Blocker\nWaiting for X\n## Unblock condition\nX completes\n")
        self.assertEqual(self.run_issues([reference(), valid]).findings["issues"], [])
        invalid = deepcopy(valid)
        invalid["body"] = "## Blocker\nWaiting for X\n"
        self.assertIn("BLOCKED_CONTRACT", {item.code for item in self.run_issues([reference(), invalid]).findings["issues"]})

    def test_closed_task_workflow_label_fails_and_pull_is_not_counted(self):
        closed = issue(1, state="closed", labels=("workflow: active", "type: task"))
        pull = issue(2, labels=("workflow: active",), pull=True)
        subject = self.run_issues([reference(), closed, pull])
        self.assertEqual(subject.data["issues"]["open_issue_count"], 1)
        self.assertIn("CLOSED_TASK_HAS_WORKFLOW", {item.code for item in subject.findings["issues"]})

    def test_reference_pinned_open_labels_and_contract(self):
        cases = (
            ([reference()], False, "REFERENCE_NOT_PINNED"),
            ([reference(state="closed")], True, "REFERENCE_CLOSED"),
            ([reference(labels=[{"name": "workflow: active"}])], True, "REFERENCE_LABELS"),
            ([reference(body="not a task contract")], True, "REFERENCE_CONTRACT"),
            ([reference(labels=[{"name": "system: reference"}, {"name": "workflow: inbox"}])], True, "REFERENCE_HAS_WORKFLOW"),
        )
        for values, pinned, code in cases:
            with self.subTest(code=code):
                self.assertIn(code, {item.code for item in self.run_issues(values, pinned=pinned).findings["issues"]})


class LabelFixtures(unittest.TestCase):
    def test_exact_labels_pass(self):
        subject = doctor()
        subject.check_labels()
        self.assertEqual(subject.findings["labels"], [])

    def test_wrong_color_description_and_missing_label_fail(self):
        api = FakeApi()
        api.labels[0]["color"] = "000000"
        api.labels[1]["description"] = "wrong"
        api.labels.pop()
        subject = doctor(api)
        subject.check_labels()
        self.assertEqual({item.code for item in subject.findings["labels"]}, {"LABEL_COLOR", "LABEL_DESCRIPTION", "LABEL_MISSING"})


class TaskBranchFixtures(unittest.TestCase):
    def run_branches(self, names, issues=None, prs=None):
        api = FakeApi()
        api.refs = [{"ref": f"refs/heads/{name}"} for name in names]
        api.issues = [reference()] + (issues or [])
        api.prs = prs or []
        subject = doctor(api)
        subject.check_task_branches()
        return {item.code for item in subject.findings["task_branches"]}

    def test_valid_branch_and_open_pr(self):
        task = issue(123, labels=("workflow: active", "type: task"), body="## Next physical action\nReview PR")
        pr = {"number": 9, "head": {"ref": "task/main/123-health-doctor"}, "base": {"ref": "main"}}
        self.assertEqual(self.run_branches(["task/main/123-health-doctor"], [task], [pr]), set())

    def test_bad_format_missing_issue_closed_issue_and_duplicate(self):
        closed = issue(2, state="closed", labels=("type: task",))
        task = issue(3, labels=("type: task",))
        codes = self.run_branches([
            "task/main/not-valid", "task/main/1-missing", "task/main/2-closed",
            "task/main/3-first", "task/linux/3-second",
        ], [closed, task])
        self.assertTrue({"TASK_BRANCH_FORMAT", "TASK_ISSUE_MISSING", "ORPHAN_TASK_BRANCH", "DUPLICATE_TASK_BRANCH"}.issubset(codes))

    def test_historical_refs_are_ignored(self):
        codes = self.run_branches(["reconcile/main/S1-B04", "fix/main/589-history"])
        self.assertEqual(codes, set())


class WorkflowAndSecurityFixtures(unittest.TestCase):
    def test_all_active_and_disabled_workflow(self):
        subject = doctor()
        subject.check_workflows()
        self.assertEqual(subject.findings["workflows"], [])
        api = FakeApi()
        api.workflows[0]["state"] = "disabled_manually"
        subject = doctor(api)
        subject.check_workflows()
        self.assertIn("WORKFLOW_DISABLED", {item.code for item in subject.findings["workflows"]})

    def test_zero_alerts_pass_and_each_severity_fails(self):
        subject = doctor()
        subject.check_security()
        self.assertEqual(subject.findings["security"], [])
        for severity in ("critical", "high", "medium", "low"):
            with self.subTest(severity=severity):
                api = FakeApi()
                api.alerts["dependabot"] = [{"security_advisory": {"severity": severity}, "dependency": {"scope": "runtime"}}]
                subject = doctor(api)
                subject.check_security()
                self.assertIn("SECURITY_ALERTS", {item.code for item in subject.findings["security"]})

    def test_development_scope_and_codeql_severity_are_grouped(self):
        api = FakeApi()
        api.alerts["dependabot"] = [{"security_advisory": {"severity": "high"}, "dependency": {"scope": "development"}}]
        api.alerts["code-scanning"] = [{"rule": {"security_severity_level": "medium"}}]
        subject = doctor(api)
        subject.check_security()
        self.assertEqual(subject.data["security"]["dependabot"]["by_scope"], {"development": 1})
        self.assertEqual(subject.data["security"]["codeql"]["by_severity"], {"medium": 1})

    def test_missing_permission_and_network_error_fail_closed(self):
        for error, code in ((HEALTH.PermissionUnknown("denied"), "UNKNOWN_PERMISSION"), (HEALTH.AuditError("network unavailable"), "SECURITY_API_ERROR")):
            with self.subTest(code=code):
                api = FakeApi()
                api.fail_contains["secret-scanning"] = error
                subject = doctor(api)
                subject._guard("security", subject.check_security)
                self.assertIn(code, {item.code for item in subject.findings["security"]})

    def test_pagination_collects_multiple_pages(self):
        class Paged(HEALTH.GitHubApi):
            def __init__(self):
                pass
            def _open(self, path, payload=None):
                page = 1 if "cursor=2" not in path else 2
                headers = {} if page == 2 else {"Link": '<https://api.github.com/repos/example/items?per_page=1&cursor=2>; rel="next"'}
                return [page], headers
        self.assertEqual(Paged().pages("repos/example/items", limit=1), [1, 2])

    def test_secret_redaction(self):
        self.assertNotIn("ghp_", HEALTH.redact("failure ghp_abcdefghijklmnopqrstuvwxyz0123456789"))
        self.assertIn("[REDACTED]", HEALTH.redact("Authorization: Bearer abc.def"))


class WorkflowContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / ".github/workflows/repository-health.yml").read_text(encoding="utf-8")

    def test_yaml_shape_schedule_dispatch_and_pr_paths(self):
        self.assertRegex(self.source, r"(?m)^name: Repository Health Doctor$")
        self.assertIn('cron: "17 6 * * *"', self.source)
        self.assertIn("workflow_dispatch:", self.source)
        self.assertIn("pull_request:", self.source)
        self.assertNotIn("pull_request_target", self.source)

    def test_permissions_are_read_only_and_actions_are_pinned(self):
        self.assertNotRegex(self.source, r"(?m)^\s+[a-z-]+:\s*write$")
        actions = HEALTH.REMOTE_ACTION.findall(self.source)
        self.assertTrue(actions)
        self.assertEqual([action for action in actions if not HEALTH.FULL_PIN.fullmatch(action)], [])

    def test_pr_has_no_live_token_and_live_checks_out_default_branch(self):
        local, live = self.source.split("  live-audit:", 1)
        self.assertIn('GITHUB_TOKEN: ""', local)
        self.assertNotIn("github.token", local)
        self.assertIn("github.event.repository.default_branch", live)
        self.assertIn("GITHUB_TOKEN: ${{ github.token }}", live)
        self.assertIn("persist-credentials: false", self.source)

    def test_timeout_concurrency_summary_and_always_artifact(self):
        self.assertIn("timeout-minutes:", self.source)
        self.assertIn("cancel-in-progress: true", self.source)
        self.assertIn("if: always()", self.source)
        self.assertIn("retention-days: 14", self.source)
        checker = CHECKER.read_text(encoding="utf-8")
        self.assertIn("GITHUB_STEP_SUMMARY", checker)

    def test_local_repository_contracts_pass(self):
        subject = doctor()
        report = subject.local()
        self.assertEqual(report["status"], "PASS", report)


if __name__ == "__main__":
    unittest.main(verbosity=2)
