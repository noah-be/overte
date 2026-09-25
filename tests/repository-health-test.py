#!/usr/bin/env python3
"""Fixture and workflow-contract tests for the Repository Health Doctor."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import importlib.util
import io
import json
import os
import re
import sys
import tempfile
import unittest
import zipfile
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
        self.branches = [{"name": name, "sha": SHA} for name in
                         json.loads((ROOT / ".github/branch-policy.json").read_text())["branches"]]
        self.prs = []
        self.workflows = [
            {"id": index + 1, "name": item["path"], "path": item["path"], "state": "active"}
            for index, item in enumerate(CONFIG["required_workflows"])
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
        if "/actions/workflows?per_page=100&page=" in path:
            return {"total_count": len(self.workflows), "workflows": self.workflows}
        if "/contents/" in path:
            return {"type": "file", "path": path.split("/contents/")[1].split("?")[0]}
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

    def branch_inventory(self, repository):
        self._failure(f"repos/{repository}/branches")
        return self.branches


def doctor(api=None):
    return HEALTH.Doctor(ROOT, deepcopy(CONFIG), api or FakeApi())


class BranchFixtures(unittest.TestCase):
    def test_all_six_edges_are_valid(self):
        subject = doctor()
        subject.check_branches()
        self.assertEqual(subject.data["branches"]["valid_edges"], 6)
        self.assertEqual(subject.findings["branches"], [])

    def test_missing_branch_and_api_error_fail_without_stopping_other_edges(self):
        api = FakeApi()
        api.fail_contains["android-phone"] = HEALTH.AuditError("simulated API failure")
        subject = doctor(api)
        subject.check_branches()
        self.assertEqual(len(subject.data["branches"]["edges"]), 5)
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

    def test_all_remote_names_are_checked_without_a_pull_request(self):
        api = FakeApi()
        invalid = ["fix/android-phone-default-microphone", "fix/android-phone-editor-teardown",
                   "experiment/android-phone-apk-size"]
        api.branches += [{"name": name, "sha": SHA} for name in invalid]
        subject = doctor(api)
        subject._guard("branches", subject.check_branches)
        findings = subject.findings["branches"]
        self.assertEqual([finding.code for finding in findings], ["BRANCH_NAME_INVALID"] * 3)
        self.assertTrue(all(any(name in finding.message for finding in findings) for name in invalid))
        data = subject.data["branches"]
        self.assertTrue(data["inventory_complete"])
        self.assertEqual((data["total_branches"], data["valid_branch_names"], data["invalid_branch_names"]), (10, 7, 3))
        self.assertEqual(api.prs, [])
        self.assertEqual(subject.report("live")["exit_code"], 1)

    def test_central_policy_accepts_permanent_scoped_task_reconcile_promotion_and_dependabot(self):
        api = FakeApi()
        names = ["fix/android-phone/microphone", "ci/ios/build", "task/ios/948-prerelease-quality-gate",
                 "reconcile/android-pico/parent-refresh", "promote/apple/shared-fix",
                 "dependabot/npm_and_yarn/tools/jsdoc/example-1.2.3"]
        api.branches += [{"name": name, "sha": SHA} for name in names]
        subject = doctor(api)
        module = subject.branch_policy_module()
        with mock.patch.object(module, "validate_branch_name", wraps=module.validate_branch_name) as validate:
            subject.check_branches()
        self.assertEqual(subject.findings["branches"], [])
        self.assertEqual({call.args[1] for call in validate.call_args_list}, {row["name"] for row in api.branches})
        self.assertEqual(validate.call_count, len(api.branches))
        self.assertEqual(subject.data["branches"]["invalid_branch_names"], 0)

    def test_inventory_errors_are_operational_not_complete_health_evidence(self):
        for error, code in ((HEALTH.AuditError("incomplete inventory"), "BRANCH_API_ERROR"),
                            (HEALTH.PermissionUnknown("permission unavailable"), "UNKNOWN_PERMISSION")):
            with self.subTest(code=code):
                api = FakeApi()
                api.fail_contains["/branches"] = error
                subject = doctor(api)
                heads = {row["name"]: row["sha"] for row in api.branches}
                admission = {"status": "READY", "heads": heads, "reasons": [], "hierarchy_synchronized": True}
                with mock.patch.object(subject, "propagation_state", return_value=admission):
                    report = subject.live_when_idle("workflow_dispatch")
                self.assertFalse(report["audit_complete"])
                self.assertIsNone(report["audit_completed_at"])
                self.assertEqual(report["exit_code"], 2)
                self.assertIn(code, {item["code"] for item in report["results"]["branches"]["findings"]})
                self.assertFalse(report["results"]["branches"]["data"]["inventory_complete"])

    def test_missing_duplicate_malformed_or_stale_inventory_fails_closed(self):
        complete = FakeApi().branches
        for inventory in (None, {}, [], complete[:-1], complete + [complete[0]],
                          complete + [None], complete + [{"name": "fix/ios/test", "sha": "invalid"}],
                          complete + [{"name": None, "sha": SHA}],
                          [{**row, "sha": "2" * 40} for row in complete]):
            with self.subTest(inventory=inventory):
                api = FakeApi()
                api.branches = inventory
                subject = doctor(api)
                subject.check_branches()
                self.assertEqual(subject.findings["branches"][0].code, "BRANCH_API_ERROR")
                self.assertEqual(subject.report("live")["exit_code"], 2)
                self.assertFalse(subject.data["branches"]["inventory_complete"])


class BranchInventoryApiFixtures(unittest.TestCase):
    def response(self, names, *, count=None, more=False, cursor=None):
        return {"data": {"repository": {"nameWithOwner": CONFIG["repository"], "refs": {
            "totalCount": len(names) if count is None else count,
            "nodes": [{"name": name, "target": {"oid": SHA}} for name in names],
            "pageInfo": {"hasNextPage": more, "endCursor": cursor},
        }}}}

    def read(self, responses):
        api = HEALTH.GitHubApi("fixture-token")
        with mock.patch.object(api, "_request", side_effect=responses) as request:
            result = api.branch_inventory(CONFIG["repository"])
        for call in request.call_args_list:
            self.assertEqual(call.args[0], "graphql")
            self.assertTrue(call.args[1]["query"].startswith("query("))
            self.assertEqual(call.args[1]["variables"]["owner"], "noah-be")
            self.assertEqual(call.args[1]["variables"]["name"], "overte")
        return result, request.call_args_list

    def test_counted_cursor_pages_return_all_branches(self):
        result, calls = self.read([self.response(["main"], count=2, more=True, cursor="next"),
                                   self.response(["fix/main/example"], count=2)])
        self.assertEqual([row["name"] for row in result], ["main", "fix/main/example"])
        self.assertIsNone(calls[0].args[1]["variables"]["cursor"])
        self.assertEqual(calls[1].args[1]["variables"]["cursor"], "next")

    def test_missing_changed_duplicate_and_nonprogressing_pages_fail_closed(self):
        variants = [
            [self.response(["main"], count=2)],
            [self.response(["main"], count=0)],
            [self.response(["main", "main"])],
            [self.response([], count=1, more=True, cursor="next")],
            [self.response(["main"], count=2, more=True)],
            [self.response(["main"], count=1, more=True, cursor="next")],
            [self.response(["main"], count=1001)],
            [self.response(["main"], count=2, more=True, cursor="next"), self.response(["fix/main/test"], count=3)],
            [self.response(["main"], count=2, more=True, cursor="next"), self.response(["main"], count=2)],
            [self.response(["main"], count=3, more=True, cursor="next"),
             self.response(["fix/main/test"], count=3, more=True, cursor="next")],
        ]
        for pages in variants:
            with self.subTest(pages=pages), self.assertRaises(HEALTH.AuditError):
                self.read(pages)

    def test_invalid_graphql_identity_shape_and_errors_fail_closed(self):
        valid = self.response(["main"])
        variants = [None, [], {}, {"data": None}, {"data": []}, {"data": {"repository": None}},
                    {"errors": [{"message": "unavailable"}]},
                    {**valid, "errors": [{"message": "partial response"}]}]
        wrong_owner = deepcopy(valid)
        wrong_owner["data"]["repository"]["nameWithOwner"] = "overte-org/overte"
        variants.append(wrong_owner)
        for key, value in (("totalCount", True), ("nodes", None), ("nodes", [None]),
                           ("nodes", [{"name": "main", "target": {"oid": "bad"}}]),
                           ("pageInfo", {"hasNextPage": "false"})):
            document = deepcopy(valid)
            document["data"]["repository"]["refs"][key] = value
            variants.append(document)
        for document in variants:
            with self.subTest(document=document), self.assertRaises(HEALTH.AuditError):
                self.read([document])

    def test_pagination_has_a_hard_bound(self):
        pages = [self.response([f"fix/main/item-{index}"], count=11, more=True, cursor=str(index))
                 for index in range(10)]
        with self.assertRaisesRegex(HEALTH.AuditError, "pagination exceeded"):
            self.read(pages)


class IssueFixtures(unittest.TestCase):
    def archived_task(self, *, workflow='active', include_next=True, archive_issue=1):
        spec = importlib.util.spec_from_file_location('doctor_archive_fixture', ROOT / 'tools/issue-intake/intake.py')
        intake = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(intake)
        policy = intake.load_policy(path=ROOT / '.github/issue-policy.json')
        historical = issue(archive_issue, body=(
            '## Next physical action\nOld action.\n\n## Next action\nAnother old action.\n\n'
            '## Blocker\nAn old dependency.\n\n## Unblock condition\nHistorical recovery.\n'))
        historical['updated_at'] = '2026-09-01T12:00:00Z'
        fields = {'summary': 'Retain the current task and its original evidence.', 'scope': 'Repository checks.',
                  'outcome': 'Audit the current workflow.', 'done_criteria': ['The current task is verified.'],
                  'dependencies': [], 'required_checks': ['Run the offline fixture.']}
        if include_next:
            fields['next_action'] = 'Review the current handoff.'
        if workflow == 'blocked':
            fields['blocker'] = 'A current dependency is unavailable.'
        draft = {'title': 'Archive fixture', 'kind': 'task', 'platforms': [], 'fields': fields,
                 'milestone': None, 'request_id': '12345678-1234-4234-8234-123456789abc',
                 'legacy': intake.archive_description(historical)}
        value = issue(1, labels=('type: task', 'workflow: ' + workflow, 'validation: passed', 'history: preserved'),
                      body=intake.render(draft, policy))
        value['title'] = draft['title']
        return value

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

    def test_verified_preserved_headings_do_not_duplicate_current_next_action(self):
        task = self.archived_task()
        original = deepcopy(task)
        subject = self.run_issues([reference(), task])
        self.assertEqual(subject.findings['issues'], [])
        self.assertEqual(task, original, 'audit must not rewrite current or preserved evidence')

    def test_preserved_history_cannot_supply_missing_current_workflow_fields(self):
        for task, expected in ((self.archived_task(include_next=False), 'NEXT_ACTION_INVALID'),
                               (self.archived_task(workflow='blocked'), 'BLOCKED_CONTRACT')):
            with self.subTest(expected=expected):
                codes = {item.code for item in self.run_issues([reference(), task]).findings['issues']}
                self.assertIn(expected, codes)

    def test_tampered_or_wrong_issue_archive_cannot_hide_current_findings(self):
        tampered = self.archived_task()
        tampered['body'] = tampered['body'].replace('Old action.', 'Altered action.')
        for task in (tampered, self.archived_task(archive_issue=999)):
            with self.subTest(body=task['body'][:40]):
                codes = {item.code for item in self.run_issues([reference(), task]).findings['issues']}
                self.assertIn('ISSUE_ARCHIVE_INVALID', codes)
                self.assertIn('ISSUE_STRUCTURE', codes)

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

    def test_terminal_security_workflow_failure_is_recorded_not_reclassified(self):
        class FailedRunApi(FakeApi):
            def get(self, path):
                if "/actions/workflows/" in path and "/runs?" in path:
                    return {"workflow_runs": [{"status": "completed", "conclusion": "failure"}]}
                return super().get(path)
        subject = doctor(FailedRunApi())
        subject.check_security()
        self.assertEqual(subject.findings["security"], [])
        self.assertEqual(set(subject.data["security"]["workflow_conclusions"].values()), {"failure"})
        rendered = HEALTH.summary(subject.report('live'))
        self.assertIn('Latest observed terminal run (not necessarily main)', rendered)
        self.assertIn('**failure**', rendered)
        self.assertIn('Overall: **PASS**', rendered)

    def test_every_operational_gate_is_registered_with_its_main_owner(self):
        inventory = {entry['path']: entry['owner_branch'] for entry in CONFIG['required_workflows']}
        for name in ('repository-checks.yml', 'parent-qualification.yml', 'sync-test-reuse.yml',
                     'sync-validation.yml', 'dependency-releases.yml'):
            with self.subTest(workflow=name):
                self.assertEqual(inventory['.github/workflows/' + name], 'main')
                api = FakeApi()
                api.workflows = [row for row in api.workflows if row['path'] != '.github/workflows/' + name]
                subject = doctor(api)
                subject.check_workflows()
                self.assertIn('WORKFLOW_MISSING', {finding.code for finding in subject.findings['workflows']})

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
        self.assertIn('cron: "17 2,8,14,20 * * *"', self.source)
        self.assertIn('timezone: "Europe/Berlin"', self.source)
        self.assertIn('--when-idle --event "$HEALTH_EVENT"', self.source)
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
        self.assertNotIn("REPOSITORY_HEALTH_READ_TOKEN", local)
        self.assertIn("github.event.repository.default_branch", live)
        self.assertIn(
            "GITHUB_TOKEN: ${{ secrets.REPOSITORY_HEALTH_READ_TOKEN || github.token }}",
            live,
        )
        self.assertIn("ref: ${{ github.sha }}", live)
        self.assertIn("HEALTH_SOURCE_SHA: ${{ github.sha }}", live)
        self.assertIn("persist-credentials: false", self.source)

    def test_timeout_concurrency_summary_and_always_artifact(self):
        self.assertIn("timeout-minutes:", self.source)
        self.assertIn("cancel-in-progress: true", self.source)
        self.assertIn("if: always()", self.source)
        self.assertIn("retention-days: 14", self.source)
        checker = CHECKER.read_text(encoding="utf-8")
        self.assertIn("GITHUB_STEP_SUMMARY", checker)

    def test_both_jobs_install_the_declared_python_dependencies(self):
        for job in self.source.split('  live-audit:'):
            self.assertIn('actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1', job)
            self.assertIn('python-version: "3.12"', job)
            self.assertIn('python3 -m pip install -r tests/requirements-repository.txt', job)
        self.assertIn('"tests/requirements-repository.txt"', self.source)

    def test_local_repository_contracts_pass(self):
        subject = doctor()
        report = subject.local()
        self.assertEqual(report["status"], "PASS", report)


class QuiescenceTests(unittest.TestCase):
    NOW = datetime(2026, 9, 6, 0, 17, tzinfo=timezone.utc)

    class Api:
        def __init__(self):
            self.prs = []
            self.runs = {}
            self.sha = SHA
            self.date = '2026-09-05T20:00:00Z'
            self.behind = 0
            self.failure = False

        def pages(self, path):
            return self.prs

        def get(self, path):
            if self.failure:
                raise HEALTH.PermissionUnknown('fixture permission denial')
            if '/git/ref/heads/' in path:
                return {'object': {'sha': self.sha}}
            if '/commits/' in path:
                return {'sha': self.sha, 'commit': {'committer': {'date': self.date}}}
            if '/compare/' in path:
                return {'behind_by': self.behind, 'status': 'diverged' if self.behind else 'identical'}
            if '/runs?status=' in path:
                status = path.split('status=')[1].split('&')[0]
                runs = self.runs.get(status, [])
                return {'total_count': len(runs), 'workflow_runs': runs}
            raise AssertionError(path)

    def subject(self):
        api = self.Api()
        subject = doctor(api)
        subject.live = mock.Mock(side_effect=lambda: subject.report('live'))
        return subject, api

    def test_busy_pr_never_invokes_audit(self):
        subject, api = self.subject()
        api.prs = [{'base': {'ref': 'apple-ios', 'repo': {'full_name': CONFIG['repository']}},
                    'head': {'ref': 'reconcile/ios/657-test', 'repo': {'full_name': CONFIG['repository']}},
                    'created_at': '2026-09-06T00:00:00Z'}]
        report = subject.live_when_idle('workflow_dispatch', lambda: self.NOW)
        self.assertEqual(report['status'], 'DEFERRED_PROPAGATION')
        self.assertFalse(report['audit_executed'])
        self.assertTrue(all(result['status'] == 'NOT_RUN' for result in report['results'].values()))
        subject.live.assert_not_called()

    def test_every_nonterminal_qualification_state_defers(self):
        for status in ('queued', 'in_progress', 'waiting', 'pending', 'requested'):
            with self.subTest(status=status):
                subject, api = self.subject()
                api.runs[status] = [{'status': status, 'head_branch': 'android-vr',
                                     'created_at': '2026-09-06T00:00:00Z'}]
                self.assertEqual(subject.live_when_idle('workflow_dispatch', lambda: self.NOW)['status'],
                                 'DEFERRED_PROPAGATION')
                subject.live.assert_not_called()

    def test_recent_unfinished_hierarchy_bridges_between_prs(self):
        subject, api = self.subject()
        api.date, api.behind = '2026-09-06T00:10:00Z', 1
        self.assertEqual(subject.live_when_idle('workflow_dispatch', lambda: self.NOW)['status'],
                         'DEFERRED_PROPAGATION')
        subject.live.assert_not_called()
        # Old unresolved drift is sent to the real audit, not deferred forever.
        api.date = '2026-09-05T20:00:00Z'
        subject.live.side_effect = lambda: subject.fail('branches', 'BRANCH_DRIFT', 'fixture') or subject.report('live')
        self.assertEqual(subject.live_when_idle('workflow_dispatch', lambda: self.NOW)['status'], 'FAIL')
        subject.live.assert_called_once()

    def test_delayed_schedule_runs_in_daytime_in_summer_and_winter(self):
        for moment in (datetime(2026, 9, 6, 10, tzinfo=timezone.utc),
                       datetime(2027, 1, 6, 6, tzinfo=timezone.utc)):
            subject, _ = self.subject()
            report = subject.live_when_idle('schedule', lambda: moment)
            self.assertEqual(report['status'], 'PASS')
            subject.live.assert_called_once()
        subject, _ = self.subject()
        self.assertEqual(subject.live_when_idle('schedule', lambda: self.NOW)['status'], 'PASS')

    def test_manual_daytime_and_final_synchronized_heads_are_allowed(self):
        subject, api = self.subject()
        api.date = '2026-09-06T00:10:00Z'
        report = subject.live_when_idle('workflow_dispatch',
            lambda: datetime(2026, 9, 6, 10, 17, tzinfo=timezone.utc))
        self.assertEqual(report['status'], 'PASS')
        self.assertTrue(report['audit_executed'] and report['admission']['accepted'])
        self.assertEqual(report['admission']['before']['heads'], report['admission']['after']['heads'])

    def test_mid_audit_head_change_cannot_produce_accepted_pass(self):
        subject, api = self.subject()
        def changed():
            api.sha = '2' * 40
            return subject.report('live')
        subject.live.side_effect = changed
        report = subject.live_when_idle('workflow_dispatch', lambda: self.NOW)
        self.assertEqual(report['status'], 'DEFERRED_REPOSITORY_CHANGED')
        self.assertFalse(report['admission']['accepted'])

    def test_head_change_never_hides_independent_security_failure(self):
        subject, api = self.subject()
        def changed():
            api.sha = '2' * 40
            subject.fail('security', 'SECURITY_ALERT', 'fixture')
            return subject.report('live')
        subject.live.side_effect = changed
        report = subject.live_when_idle('workflow_dispatch', lambda: self.NOW)
        self.assertEqual(report['status'], 'FAIL')
        self.assertFalse(report['admission']['accepted'])

    def test_unreadable_or_stale_activity_fails_closed(self):
        subject, api = self.subject()
        api.failure = True
        with self.assertRaises(HEALTH.AuditError):
            subject.live_when_idle('workflow_dispatch', lambda: self.NOW)
        subject.live.assert_not_called()
        api.failure = False
        api.runs['in_progress'] = [{'status': 'in_progress', 'head_branch': 'main',
                                    'created_at': '2026-09-05T20:00:00Z'}]
        with self.assertRaisesRegex(HEALTH.AuditError, 'two-hour'):
            subject.live_when_idle('workflow_dispatch', lambda: self.NOW)

    def test_incomplete_activity_and_invalid_head_never_admit(self):
        subject, api = self.subject()
        api.sha = 'not-a-sha'
        with self.assertRaisesRegex(HEALTH.AuditError, 'invalid permanent head'):
            subject.live_when_idle('workflow_dispatch', lambda: self.NOW)
        subject, api = self.subject()
        original = api.get
        api.get = lambda path: {'total_count': 101, 'workflow_runs': []} if '/runs?' in path else original(path)
        with self.assertRaisesRegex(HEALTH.AuditError, 'incomplete'):
            subject.live_when_idle('workflow_dispatch', lambda: self.NOW)
        subject.live.assert_not_called()

    def test_new_propagation_during_audit_invalidates_report(self):
        subject, api = self.subject()
        def started():
            api.runs['queued'] = [{'status': 'queued', 'head_branch': 'main',
                                    'created_at': '2026-09-06T00:00:00Z'}]
            return subject.report('live')
        subject.live.side_effect = started
        report = subject.live_when_idle('workflow_dispatch', lambda: self.NOW)
        self.assertEqual(report['status'], 'DEFERRED_REPOSITORY_CHANGED')
        self.assertFalse(report['admission']['accepted'])

    def test_complete_failure_and_operational_failure_have_different_completion(self):
        for code, complete in (('BRANCH_DRIFT', True), ('UNKNOWN_PERMISSION', False)):
            with self.subTest(code=code):
                subject, api = self.subject()
                def audited():
                    subject.executed.update(HEALTH.AREAS)
                    subject.fail('branches', code, 'fixture')
                    return subject.report('live')
                subject.live.side_effect = audited
                report = subject.live_when_idle('schedule', lambda: self.NOW)
                self.assertEqual(report['status'], 'FAIL')
                self.assertEqual(report['audit_complete'], complete)
                self.assertEqual(report['audit_completed_at'] is not None, complete)

    def test_stale_checked_out_main_defers_before_running(self):
        subject, _ = self.subject()
        with mock.patch.dict(os.environ, {'HEALTH_SOURCE_SHA': '2' * 40}):
            report = subject.live_when_idle('schedule', lambda: self.NOW)
        self.assertEqual(report['status'], 'DEFERRED_SOURCE_CHANGED')
        subject.live.assert_not_called()

    def test_final_admission_error_preserves_audit_failure(self):
        subject, api = self.subject()
        def audited():
            subject.executed.update(HEALTH.AREAS)
            subject.fail('security', 'SECURITY_ALERTS', 'fixture')
            api.failure = True
            return subject.report('live')
        subject.live.side_effect = audited
        report = subject.live_when_idle('schedule', lambda: self.NOW)
        self.assertEqual(report['status'], 'FAIL')
        self.assertTrue(report['audit_executed'])
        self.assertFalse(report['audit_complete'])
        self.assertEqual(report['results']['security']['findings'][0]['code'], 'SECURITY_ALERTS')

    def test_legacy_live_cli_cannot_bypass_admission(self):
        report = doctor().report('live')
        with tempfile.TemporaryDirectory(prefix='overte-health-cli-') as directory:
            output = Path(directory) / 'report.json'
            with mock.patch.object(sys, 'argv', [str(CHECKER), '--report', str(output)]), \
                 mock.patch.object(HEALTH, 'GitHubApi', return_value=self.Api()), \
                 mock.patch.object(HEALTH.Doctor, 'live_when_idle', return_value=report) as admitted, \
                 mock.patch.object(HEALTH.Doctor, 'live', side_effect=AssertionError('admission bypass')), \
                 mock.patch('builtins.print'), mock.patch.dict(os.environ, {'GITHUB_STEP_SUMMARY': ''}):
                self.assertEqual(HEALTH.main(), 0)
                admitted.assert_called_once_with('workflow_dispatch')
                self.assertEqual(json.loads(output.read_text())['status'], 'PASS')


class EvidenceFixtures(unittest.TestCase):
    NOW = datetime(2026, 9, 24, 14, tzinfo=timezone.utc)

    @classmethod
    def report(cls, status='PASS'):
        return {
            'schema': 2, 'repository': CONFIG['repository'], 'mode': 'live',
            'status': status, 'exit_code': 0 if status == 'PASS' else 1,
            'source_sha': SHA, 'run_id': '123', 'run_attempt': '1',
            'generated_at': HEALTH.timestamp(cls.NOW),
            'audit_executed': True, 'audit_complete': True,
            'audit_started_at': HEALTH.timestamp(cls.NOW - timedelta(minutes=5)),
            'audit_completed_at': HEALTH.timestamp(cls.NOW - timedelta(minutes=1)),
            'admission': {'accepted': True, **{
                side: {'heads': {name: SHA for name in doctor().policy()}}
                for side in ('before', 'after')}},
            'results': {area: {'status': 'PASS', 'findings': [], 'data': {}} for area in HEALTH.AREAS},
        }

    class Api:
        def __init__(self, report):
            self.report = report
            self.run = {
                'id': 123, 'run_attempt': 1, 'event': 'schedule', 'head_sha': SHA,
                'head_branch': 'main', 'workflow_id': 7,
                'path': CONFIG['freshness']['workflow_path'],
                'repository': {'full_name': CONFIG['repository']},
                'head_repository': {'full_name': CONFIG['repository']},
                'created_at': '2026-09-24T13:50:00Z',
                'updated_at': '2026-09-24T14:00:00Z',
                'conclusion': 'success', 'status': 'completed',
            }
            self.artifacts = [{'id': 456, 'expired': False, 'name': 'repository-health-report-123-1',
                               'workflow_run': {'id': 123, 'head_sha': SHA}}]

        def get(self, path):
            if path == f"repos/{CONFIG['repository']}":
                return {'full_name': CONFIG['repository'], 'default_branch': 'main'}
            if path.endswith('/actions/workflows/repository-health.yml'):
                return {'id': 7, 'state': 'active', 'path': CONFIG['freshness']['workflow_path']}
            if '/runs?' in path:
                return {'total_count': 1, 'workflow_runs': [self.run]}
            if '/artifacts?' in path:
                return {'total_count': len(self.artifacts), 'artifacts': self.artifacts}
            raise AssertionError(path)

        def artifact_report(self, repository, artifact_id):
            assert repository == CONFIG['repository'] and artifact_id == 456
            return self.report

    def assess(self, report=None, api=None, now=None):
        return HEALTH.freshness(CONFIG, api or self.Api(report or self.report()), now or self.NOW)

    def test_full_failed_audit_is_fresh_without_claiming_pass(self):
        report = self.report('FAIL')
        report['results']['branches'].update(status='FAIL', findings=[{'code': 'BRANCH_DRIFT', 'message': 'fixture'}])
        api = self.Api(report)
        api.run['conclusion'] = 'failure'
        result = self.assess(api=api)
        self.assertEqual(result['status'], 'FRESH')
        self.assertEqual(result['last_complete_status'], 'FAIL')
        self.assertEqual(result['source_run_id'], '123')

    def test_green_deferred_workflow_does_not_refresh_evidence(self):
        report = self.report()
        report.update(status='DEFERRED_PROPAGATION', audit_complete=False, audit_executed=False)
        result = self.assess(report)
        self.assertEqual(result['status'], 'MISSING')
        self.assertIsNone(result['last_complete_at'])

    def test_stale_and_expired_evidence_fail(self):
        self.assertEqual(self.assess(now=self.NOW + timedelta(hours=31))['status'], 'STALE')
        api = self.Api(self.report())
        api.artifacts[0]['expired'] = True
        self.assertEqual(self.assess(api=api)['status'], 'MISSING')
        api.artifacts = []
        self.assertEqual(self.assess(api=api)['status'], 'MISSING')

    def test_wrong_repository_sha_attempt_and_incomplete_report_fail_closed(self):
        for field, value in (('repository', 'elsewhere/overte'), ('source_sha', '2' * 40),
                             ('run_attempt', '2'), ('mode', 'local')):
            with self.subTest(field=field):
                report = self.report()
                report[field] = value
                self.assertEqual(self.assess(report)['status'], 'UNKNOWN')
        report = self.report()
        report['results']['security']['status'] = 'NOT_RUN'
        self.assertEqual(self.assess(report)['status'], 'UNKNOWN')
        report = self.report('FAIL')
        report['results']['security'].update(status='FAIL', findings=[{'code': 'UNKNOWN_PERMISSION'}])
        self.assertEqual(self.assess(report)['status'], 'UNKNOWN')

    def test_fork_run_or_other_workflow_is_not_trusted(self):
        for key, value in (('head_repository', {'full_name': 'stranger/overte'}),
                           ('path', '.github/workflows/other.yml'), ('head_branch', 'topic')):
            with self.subTest(key=key):
                api = self.Api(self.report())
                api.run[key] = value
                self.assertEqual(self.assess(api=api)['status'], 'UNKNOWN')
        api = self.Api(self.report())
        api.run['event'] = 'pull_request'
        self.assertEqual(self.assess(api=api)['status'], 'MISSING')

    def test_future_or_invalid_timestamp_cannot_refresh(self):
        for field, value in (('generated_at', '2026-09-25T00:00:00Z'),
                             ('audit_completed_at', '2026-09-24T13:00:00Z'),
                             ('audit_started_at', 'not a timestamp')):
            with self.subTest(field=field):
                report = self.report()
                report[field] = value
                self.assertEqual(self.assess(report)['status'], 'UNKNOWN')

    def test_permission_failure_is_unknown_not_missing_or_fresh(self):
        api = self.Api(self.report())
        api.get = mock.Mock(side_effect=HEALTH.PermissionUnknown('fixture'))
        self.assertEqual(self.assess(api=api)['status'], 'UNKNOWN')

    def test_older_run_artifacts_are_not_downloaded_after_newest_complete_proof(self):
        api = self.Api(self.report())
        older = deepcopy(api.run)
        older.update(id=122, created_at='2026-09-23T12:00:00Z', updated_at='2026-09-23T13:00:00Z')
        original = api.get
        def get(path):
            if '/runs?' in path:
                # Do not depend on provider ordering, including old reruns.
                return {'total_count': 2, 'workflow_runs': [older, api.run]}
            if '/runs/122/artifacts?' in path:
                self.fail('older artifact lookup is unnecessary')
            return original(path)
        api.get = get
        result = self.assess(api=api)
        self.assertEqual(result['status'], 'FRESH')
        self.assertEqual(result['artifact_inventories_read'], 1)

    def test_newer_malformed_artifact_cannot_be_hidden_by_recent_complete_audit(self):
        api = self.Api(self.report())
        newer = deepcopy(api.run)
        newer.update(id=124, status='in_progress')
        original = api.get
        def get(path):
            if '/runs?' in path:
                return {'total_count': 2, 'workflow_runs': [api.run, newer]}
            if '/runs/124/artifacts?' in path:
                return {'total_count': 1, 'artifacts': [{'id': 457, 'expired': False,
                    'name': 'repository-health-report-124-1', 'workflow_run': {'id': 999, 'head_sha': SHA}}]}
            return original(path)
        api.get = get
        self.assertEqual(self.assess(api=api)['status'], 'UNKNOWN')

    def test_repeated_missing_evidence_has_a_fail_closed_query_budget(self):
        api = self.Api(self.report())
        original = api.get
        def get(path):
            if '/runs?' in path:
                return {'total_count': 100, 'workflow_runs': [dict(api.run, id=index) for index in range(100)]}
            if '/artifacts?' in path:
                return {'total_count': 0, 'artifacts': []}
            return original(path)
        api.get = get
        result = self.assess(api=api)
        self.assertEqual(result['status'], 'UNKNOWN')
        self.assertEqual(result['artifact_inventories_read'], HEALTH.MAX_FRESHNESS_ARTIFACT_READS)
        self.assertIn('budget', result['findings'][0]['message'])

    def test_local_audit_only_reports_executed_contracts(self):
        report = doctor().local()
        self.assertFalse(report['audit_executed'])
        self.assertFalse(report['audit_complete'])
        for area, value in report['results'].items():
            self.assertEqual(value['status'], 'PASS' if area == 'repository_contracts' else 'NOT_RUN')

    def test_report_download_rejects_extra_or_traversal_members(self):
        for names in (['../repository-health-report.json'], ['repository-health-report.json', 'extra']):
            with self.subTest(names=names):
                data = io.BytesIO()
                with zipfile.ZipFile(data, 'w') as archive:
                    for name in names:
                        archive.writestr(name, '{}')
                response = mock.MagicMock()
                response.__enter__.return_value.read.return_value = data.getvalue()
                opener = mock.Mock()
                opener.open.return_value = response
                with mock.patch.object(HEALTH, 'build_opener', return_value=opener):
                    with self.assertRaises(HEALTH.AuditError):
                        HEALTH.GitHubApi('fixture-token').artifact_report(CONFIG['repository'], 456)

    def test_artifact_redirect_strips_authentication(self):
        response = mock.MagicMock()
        data = io.BytesIO()
        with zipfile.ZipFile(data, 'w') as archive:
            archive.writestr('repository-health-report.json', '{}')
        response.__enter__.return_value.read.return_value = data.getvalue()
        opener = mock.Mock()
        opener.open.return_value = response
        with mock.patch.object(HEALTH, 'build_opener', return_value=opener) as build:
            HEALTH.GitHubApi('fixture-token').artifact_report(CONFIG['repository'], 456)
        redirect = build.call_args.args[0]
        request = HEALTH.Request('https://api.github.com/example', headers={'Authorization': 'fixture-token'})
        target = redirect.redirect_request(request, None, 302, 'Found', {}, 'https://example.blob.core.windows.net/report')
        self.assertFalse(target.has_header('Authorization'))
        with self.assertRaises(HEALTH.AuditError):
            redirect.redirect_request(request, None, 302, 'Found', {}, 'http://example.test/report')

    def test_renaming_workflow_display_name_does_not_hide_registration(self):
        api = FakeApi()
        for workflow in api.workflows:
            workflow['name'] = 'New display name'
        subject = doctor(api)
        subject.check_workflows()
        self.assertEqual(subject.findings['workflows'], [])

    def test_product_owned_workflows_are_not_required_on_main(self):
        entries = {item['path']: item['owner_branch'] for item in CONFIG['required_workflows']}
        self.assertEqual(entries['.github/workflows/android-tests.yml'], 'android-main')
        self.assertEqual(entries['.github/workflows/apple-branch-topology.yml'], 'apple-main')
        self.assertNotIn('.github/workflows/desktop-branch-topology.yml', entries)



if __name__ == "__main__":
    unittest.main(verbosity=2)
