#!/usr/bin/env python3
"""Behavioral tests: rejected writes, ownership, concurrency, retries and round trips."""
import copy
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/issue-intake"))
SPEC = importlib.util.spec_from_file_location("intake", ROOT / "tools/issue-intake/intake.py")
intake = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(intake)
sys.modules["intake"] = intake
GUARD_SPEC = importlib.util.spec_from_file_location("guard", ROOT / "tools/issue-intake/guard.py")
guard = importlib.util.module_from_spec(GUARD_SPEC)
GUARD_SPEC.loader.exec_module(guard)
POLICY = intake.load_policy(path=ROOT / ".github/issue-policy.json")


def draft(kind="bug"):
    value = {"request_id": "ecf3f3c7-f1d6-4cd3-9607-e1871561802d", "title": "Startup overlay briefly flashes", "kind": kind,
             "platforms": ["android phone"], "milestone": None,
             "fields": {"summary": "An unintended square appears during startup.", "expected": "Startup displays only intended controls.",
                        "reproduction": "Unknown", "environment": "Unknown"}}
    if kind in ("task", "acceptance"):
        value["fields"].update(scope="Startup overlay only; no world-loading redesign.", outcome="The startup overlay follows the documented visibility condition.",
                               done_criteria=["No unintended square appears during startup."], required_checks=["Record startup on the identified candidate."])
    if kind == "idea":
        value["fields"]["benefit"] = "Reduce confusing startup transitions."
    if kind == "acceptance":
        value["milestone"] = 2
        value["fields"].update(acceptance_status="No full acceptance recorded", candidate="No milestone candidate selected", remaining="Verify the complete criterion on the pinned candidate")
    return value


def issue(value=None, number=100, state="inbox"):
    value = value or draft()
    return {"number": number, "title": value["title"], "body": intake.render(value, POLICY),
            "repository_url": "https://api.github.com/repos/noah-be/overte",
            "html_url": f"https://github.com/noah-be/overte/issues/{number}", "state": "open", "state_reason": None,
            "labels": [{"name": x} for x in intake.expected_labels(value, POLICY, state)],
            "milestone": {"number": value["milestone"]} if value.get("milestone") else None, "updated_at": "2026-09-14T09:00:00Z"}


class FakeGitHub:
    def __init__(self):
        self.rows = {}
        self.writes = []
        self.owner = intake.REPOSITORY
        self.available_labels = set(POLICY["kinds"].values()) | set(POLICY["platforms"]) | set(POLICY["validation_labels"].values()) | {"workflow: " + x for x in POLICY["states"]} | {"help wanted", "enhancement"}
        self.available_labels |= {POLICY["history_label"]} | set(POLICY["acceptance_labels"].values())
        self.milestones = {2: {"number": 2, "title": "PHONE-P1", "state": "open", "description": "Original milestone requirements", "url": "https://api.github.com/" + intake.API + "/milestones/2"}}
        self.corrupt_readback = False
        self.comments = {}
        self.client = intake.Client(self.call)

    def call(self, path, method="GET", data=None):
        if method != "GET":
            self.writes.append((path, method, copy.deepcopy(data)))
        if path == intake.API:
            return {"full_name": self.owner, "default_branch": "main"}
        if path.startswith(intake.API + "/labels?"):
            return [{"name": x} for x in self.available_labels]
        if path.startswith(intake.API + "/issues?"):
            rows = self.rows.values()
            return copy.deepcopy([x for x in rows if "state=all" in path or x["state"] == "open"])
        if path.startswith(intake.API + "/milestones?"):
            return copy.deepcopy(list(self.milestones.values()))
        if path.startswith(intake.API + "/milestones/"):
            row = self.milestones[int(path.rsplit("/", 1)[1])]
            if data:
                row.update(data)
            return copy.deepcopy(row)
        if "/comments" in path:
            if "/issues/comments/" in path:
                comment_id = int(path.rsplit("/", 1)[1])
                if method == "PATCH":
                    self.comments[comment_id].update(data)
                return copy.deepcopy(self.comments[comment_id])
            number = int(path.split("/issues/", 1)[1].split("/", 1)[0])
            issue_url = f"https://api.github.com/{intake.API}/issues/{number}"
            if method == "POST":
                comment_id = max(self.comments, default=0) + 1
                self.comments[comment_id] = {"id": comment_id, "body": data["body"], "user": {"login": "github-actions[bot]"}, "issue_url": issue_url}
                return copy.deepcopy(self.comments[comment_id])
            return copy.deepcopy([x for x in self.comments.values() if x["issue_url"] == issue_url])
        if path == intake.API + "/issues" and method == "POST":
            number = max(self.rows, default=99) + 1
            row = issue(number=number)
            self.rows[number] = row
        elif path.startswith(intake.API + "/issues/"):
            number = int(path.rsplit("/", 1)[1])
            row = self.rows[number]
        else:
            raise AssertionError((path, method, data))
        if data:
            row.update(copy.deepcopy(data))
            row["labels"] = [{"name": x} for x in data.get("labels", intake.labels(row))]
            if "milestone" in data:
                row["milestone"] = {"number": data["milestone"]} if data.get("milestone") else None
            if self.corrupt_readback:
                row["labels"] = []
        return copy.deepcopy(row)


class IntakeTests(unittest.TestCase):
    def setUp(self):
        self.api = FakeGitHub()

    def test_all_four_kinds_roundtrip(self):
        for kind in POLICY["kinds"]:
            value = draft(kind)
            self.assertEqual(intake.validate(value, POLICY), [])
            self.assertEqual(intake.parse(issue(value), POLICY), value)

    def test_extra_section_separators_preserve_field_markdown(self):
        for kind in POLICY["kinds"]:
            for separator in ("\n\n\n", "\n \n\t\n\n"):
                with self.subTest(kind=kind, separator=repr(separator)):
                    value = draft(kind)
                    value["fields"]["summary"] = ("First paragraph.  \nContinued line.\n\n\n"
                        "### Nested heading\n\n```text\nline\n\n\n  ## Literal example\n```\n\nLast paragraph.")
                    original = issue(value)
                    original["body"] = original["body"].replace("\n\n## ", separator + "## ")
                    body = original["body"]
                    self.assertEqual(intake.parse(original, POLICY), value)
                    self.assertEqual(original["body"], body)

    def test_section_spacing_does_not_hide_unknown_duplicate_or_stray_text(self):
        for unexpected in ("## Unknown section\n\nUnmapped content.",
                           "## Platforms\n\nios", "Unstructured introduction."):
            original = issue()
            original["body"] = original["body"].replace("\n\n## Issue type", "\n\n" + unexpected + "\n\n\n## Issue type")
            with self.subTest(unexpected=unexpected), self.assertRaises(intake.IntakeError):
                intake.parse(original, POLICY)
        for suffix in ("\nUser observation.", "\n\n## Expected behavior\n\nUnstructured appendix."):
            original = issue()
            original["body"] = original["body"].replace("\n\n## Expected behavior", "\n\n\n## Expected behavior") + suffix
            with self.subTest(suffix=suffix), self.assertRaises(intake.IntakeError):
                intake.parse(original, POLICY)

    def test_comparison_preserves_fenced_heading_whitespace(self):
        for opening, closing in (("```markdown", "```"), ("~~~~", "~~~~~"), ("   ````", "   ````")):
            text = opening + "\ncontent\n\n\n## Example\n\ninside\n" + closing
            body = text + "\n\n\n## Actual section\n\nvalue\n"
            self.assertEqual(intake.section_spacing_for_comparison(body), text + "\n\n## Actual section\n\nvalue\n")
            value = draft(); value["fields"]["summary"] = text
            self.assertTrue(intake.validate(value, POLICY))  # Reserved headings stay unsupported inside fields.

    def test_cli_show_and_update_repair_only_section_spacing(self):
        original = issue()
        canonical = original["body"]
        original["body"] = canonical.replace("\n\n## Expected behavior", "\n\n\n## Expected behavior")
        self.api.rows[100] = copy.deepcopy(original)

        def fake_gh(args, **kwargs):
            self.assertEqual(args[:4], ["gh", "api", "--hostname", "github.com"])
            response = self.api.call(args[6], args[5], json.loads(kwargs["input"]) if kwargs["input"] else None)
            return subprocess.CompletedProcess(args, 0, json.dumps(response), "")

        def cli(*args):
            output = io.StringIO()
            argv = ["overte-issue", "--policy", str(ROOT / ".github/issue-policy.json"), *args]
            with mock.patch.object(sys, "argv", argv), contextlib.redirect_stdout(output):
                self.assertEqual(intake.main(), 0)
            return json.loads(output.getvalue())

        with tempfile.TemporaryDirectory() as directory, mock.patch.dict(os.environ, {"XDG_CACHE_HOME": directory}), mock.patch.object(intake.subprocess, "run", side_effect=fake_gh):
            shown = cli("show", "100")
            self.assertEqual(shown["draft"], draft())
            self.assertEqual(shown["issue"], original)
            self.assertEqual(shown["validation"]["status"], "valid")
            self.assertEqual(shown["snapshot"], intake.snapshot(original))
            self.assertEqual(self.api.writes, [])
            path = Path(directory) / "draft.json"
            path.write_text(json.dumps(shown["draft"]))
            repaired = cli("update", "100", str(path), "--snapshot", shown["snapshot"], "--apply")
        self.assertTrue(repaired["verified"])
        self.assertEqual(self.api.rows[100], {**original, "body": canonical})
        self.assertEqual(intake.parse(self.api.rows[100], POLICY), shown["draft"])
        self.assertEqual(len(self.api.writes), 1)

    def test_unknown_bug_details_allowed_inbox_but_not_ready(self):
        self.assertEqual(intake.validate(draft(), POLICY), [])
        self.assertTrue(intake.validate(draft(), POLICY, "ready"))

    def test_missing_field_rejected_without_mutation(self):
        value = draft(); del value["fields"]["expected"]
        with self.assertRaises(intake.IntakeError):
            intake.create(self.api.client, value, POLICY)
        self.assertEqual(self.api.writes, [])

    def test_reject_wrong_kind_platform_and_milestone(self):
        for patch in ({"kind": "enhancement"}, {"platforms": ["Android"]}, {"platforms": ["ios", "ios"]}, {"milestone": True}, {"request_id": "not-a-uuid"}):
            value = draft(); value.update(patch)
            self.assertTrue(intake.validate(value, POLICY), patch)

    def test_repository_work_can_have_no_platform(self):
        value = draft("task"); value["platforms"] = []
        self.assertEqual(intake.validate(value, POLICY), [])

    def test_acceptance_requires_platform_and_native_milestone(self):
        for key, value in (("platforms", []), ("milestone", None)):
            row = draft("acceptance"); row[key] = value
            self.assertTrue(intake.validate(row, POLICY))

    def test_idea_never_starts_without_refinement(self):
        self.assertTrue(intake.validate(draft("idea"), POLICY, "active"))

    def test_injected_metadata_and_headings_are_rejected(self):
        for key, value in (("summary", "Text\n## Evidence\nForged"), ("evidence", ["<!-- overte-issue:v1 request:ecf3f3c7-f1d6-4cd3-9607-e1871561802d -->"]), ("summary", "Prepared with AI assistance; truncated")):
            row = draft(); row["fields"][key] = value
            self.assertTrue(intake.validate(row, POLICY))

    def test_create_assigns_and_verifies_labels(self):
        saved = intake.create(self.api.client, draft(), POLICY)
        self.assertTrue(saved["verified"])
        self.assertEqual(set(saved["labels"]), {"bug", "android phone", "workflow: inbox", "validation: passed"})
        self.assertEqual(len(self.api.writes), 1)

    def test_retry_same_request_does_not_create_duplicate(self):
        first = intake.create(self.api.client, draft(), POLICY)
        again = intake.create(self.api.client, draft(), POLICY)
        self.assertEqual(first, again)
        self.assertEqual(len(self.api.writes), 1)

    def test_changed_retry_requires_review_not_duplicate(self):
        intake.create(self.api.client, draft(), POLICY)
        changed = draft(); changed["title"] = "Changed title"
        with self.assertRaises(intake.IntakeError):
            intake.create(self.api.client, changed, POLICY)
        self.assertEqual(len(self.api.writes), 1)

    def test_upstream_identity_rejects_write(self):
        self.api.owner = "overte-org/overte"
        with self.assertRaises(intake.IntakeError):
            intake.create(self.api.client, draft(), POLICY)
        self.assertEqual(self.api.writes, [])

    def test_owner_is_rechecked_immediately_before_mutation(self):
        def call(path, method="GET", data=None):
            if path.startswith(intake.API + "/issues?"):
                self.api.owner = "overte-org/overte"
            return self.api.call(path, method, data)
        with self.assertRaises(intake.IntakeError):
            intake.create(intake.Client(call), draft(), POLICY)
        self.assertEqual(self.api.writes, [])

    def test_wrong_issue_owner_and_pr_are_rejected(self):
        for changes in ({"repository_url": "https://api.github.com/repos/overte-org/overte"}, {"pull_request": {}}):
            self.api.rows[100] = issue(); self.api.rows[100].update(changes)
            with self.assertRaises(intake.IntakeError):
                self.api.client.issue(100)

    def test_missing_repository_label_rejects_before_post(self):
        self.api.available_labels.remove("bug")
        with self.assertRaises(intake.IntakeError):
            intake.create(self.api.client, draft(), POLICY)
        self.assertEqual(self.api.writes, [])

    def test_readback_mismatch_does_not_report_success(self):
        self.api.corrupt_readback = True
        with self.assertRaises(intake.IntakeError):
            intake.create(self.api.client, draft(), POLICY)
        self.assertEqual(len(self.api.writes), 1)

    def test_supplementary_labels_survive_update(self):
        original = issue(); original["labels"].append({"name": "help wanted"})
        self.api.rows[100] = original
        changed = draft(); changed["title"] = "Startup square flashes in upper-right corner"
        result = intake.update(self.api.client, 100, changed, POLICY, intake.snapshot(original))
        self.assertIn("help wanted", result["labels"])

    def test_concurrent_edit_rejects_stale_snapshot(self):
        original = issue(); token = intake.snapshot(original)
        original["body"] += "\nUser added an observation."
        self.api.rows[100] = original
        with self.assertRaises(intake.IntakeError):
            intake.update(self.api.client, 100, draft(), POLICY, token)
        self.assertEqual(self.api.writes, [])

    def test_unstructured_manual_text_is_never_silently_dropped(self):
        original = issue(); original["body"] += "\nUser added an observation."
        with self.assertRaises(intake.IntakeError):
            intake.parse(original, POLICY)

    def test_wip_limit_counts_legacy_tasks(self):
        self.api.rows = {n: issue(number=n, state="active") for n in range(101, 104)}
        for row in self.api.rows.values():
            row["body"] = "Legacy work"
        value = draft("task")
        value["fields"].update(next_action="Record one startup video.", dependencies=[])
        self.api.rows[100] = issue(value)
        with self.assertRaises(intake.IntakeError):
            intake.update(self.api.client, 100, value, POLICY, intake.snapshot(self.api.rows[100]), "active")
        self.assertEqual(self.api.writes, [])

    def test_blocked_requires_real_blocker_and_unblock_condition(self):
        value = draft(); value["fields"].update(blocker="Unknown", unblock_condition="Unknown")
        self.assertTrue(intake.validate(value, POLICY, "blocked"))

    def test_close_completed_requires_evidence(self):
        value = draft("task"); self.api.rows[100] = issue(value)
        with self.assertRaises(intake.IntakeError):
            intake.update(self.api.client, 100, value, POLICY, intake.snapshot(self.api.rows[100]), close_reason="completed")
        self.assertEqual(self.api.writes, [])

    def test_not_planned_close_removes_workflow_without_claiming_completion(self):
        value = draft("idea"); value["fields"]["outcome"] = "Rejected because the existing startup display already covers this use case."
        self.api.rows[100] = issue(value)
        result = intake.update(self.api.client, 100, value, POLICY, intake.snapshot(self.api.rows[100]), close_reason="not_planned")
        self.assertFalse(any(x.startswith("workflow:") for x in result["labels"]))
        self.assertEqual(self.api.rows[100]["state_reason"], "not_planned")

    def test_missing_workflow_fails_managed_audit(self):
        original = issue(); original["labels"] = [x for x in original["labels"] if not x["name"].startswith("workflow:")]
        self.assertEqual(intake.inspect_issue(original, POLICY)["status"], "invalid")

    def test_passed_label_cannot_override_invalid_body(self):
        original = issue(); original["body"] = original["body"].replace("Startup displays only intended controls.", "TODO")
        self.assertEqual(intake.inspect_issue(original, POLICY)["status"], "invalid")

    def test_legacy_issue_is_reported_without_mutation(self):
        original = issue(); original["body"] = "Old issue with valuable history"; original["labels"] = [{"name": "bug"}]
        self.assertEqual(intake.inspect_issue(original, POLICY)["status"], "legacy")

    def test_removed_marker_still_fails_shared_health_validation(self):
        original = issue(); original["body"] = "Structured marker was removed"
        self.assertEqual(intake.inspect_issue(original, POLICY)["status"], "invalid")

    def test_empty_example_cannot_be_submitted(self):
        for kind in POLICY["kinds"]:
            self.assertTrue(intake.validate(intake.example(kind, POLICY), POLICY))

    def test_not_planned_requires_a_recorded_reason(self):
        self.assertTrue(intake.validate(draft("idea"), POLICY, not_planned=True))


class GuardTests(unittest.TestCase):
    def test_reconcile_updates_one_bot_comment_and_preserves_human_comment(self):
        api = FakeGitHub(); row = issue()
        row["body"] = row["body"].replace("Startup displays only intended controls.", "TODO")
        api.rows[100] = row
        api.comments[1] = {"id": 1, "body": intake.COMMENT_MARKER + " Human copied a marker.", "user": {"login": "noah-be"}, "issue_url": f"https://api.github.com/{intake.API}/issues/100"}
        human = copy.deepcopy(api.comments[1])
        guard.reconcile(api.client, 100, POLICY, apply=True, event_number=100)
        self.assertEqual(len(api.comments), 2)
        self.assertEqual(api.comments[1], human)
        writes = len(api.writes)
        guard.reconcile(api.client, 100, POLICY, apply=True, event_number=100)
        self.assertEqual(len(api.writes), writes)
        api.rows[100]["body"] = intake.render(draft(), POLICY)
        guard.reconcile(api.client, 100, POLICY, apply=True, event_number=100)
        self.assertEqual(len(api.comments), 2)
        self.assertIn("No corrections", api.comments[2]["body"])
        self.assertEqual(api.comments[1], human)

    def test_valid_reconcile_is_silent(self):
        api = FakeGitHub(); api.rows[100] = issue()
        guard.reconcile(api.client, 100, POLICY, apply=True, event_number=100)
        self.assertEqual(api.writes, [])

    def test_dry_run_does_not_write(self):
        api = FakeGitHub(); api.rows[100] = issue(state="active")
        result = guard.reconcile(api.client, 100, POLICY, apply=False)
        self.assertTrue(result["errors"])
        self.assertEqual(api.writes, [])

    def test_legacy_issue_is_preserved(self):
        row = issue(); row["body"] = "Existing unstructured history"
        row["labels"] = [{"name": "bug"}]; row["created_at"] = "2026-09-13T12:00:00Z"
        self.assertFalse(guard.plan(row, POLICY, [row])["managed"])

    def test_new_direct_issue_is_quarantined_without_body_rewrite(self):
        row = issue(); row["body"] = "Please fix this"; row["labels"] = []
        row["created_at"] = "2026-09-15T12:00:00Z"
        result = guard.plan(row, POLICY, [row])
        self.assertTrue(result["managed"])
        self.assertIn("validation: needs-info", result["patch"]["labels"])
        self.assertIn("workflow: inbox", result["patch"]["labels"])
        self.assertNotIn("body", result["patch"])

    def test_deleted_marker_does_not_escape_guard(self):
        row = issue(); row["body"] = "Malformed text"
        self.assertTrue(guard.plan(row, POLICY, [row])["managed"])

    def test_missing_workflow_is_restored(self):
        row = issue(); row["labels"] = [x for x in row["labels"] if not x["name"].startswith("workflow:")]
        result = guard.plan(row, POLICY, [row])
        self.assertEqual(result["errors"], [])
        self.assertIn("workflow: inbox", result["patch"]["labels"])

    def test_wrong_platform_label_is_repaired_from_documented_scope(self):
        row = issue(); row["labels"].append({"name": "ios"})
        result = guard.plan(row, POLICY, [row])
        self.assertNotIn("ios", result["patch"]["labels"])

    def test_malformed_active_entry_returns_to_inbox(self):
        row = issue(state="active")
        result = guard.plan(row, POLICY, [row])
        self.assertIn("workflow: inbox", result["patch"]["labels"])
        self.assertNotIn("workflow: active", result["patch"]["labels"])

    def test_unverified_completed_closure_reopens_for_correction(self):
        row = issue(); row.update(state="closed", state_reason="completed", labels=[{"name": "bug"}])
        result = guard.plan(row, POLICY, [])
        self.assertEqual(result["patch"]["state"], "open")
        self.assertIn("validation: needs-info", result["patch"]["labels"])

    def test_rejected_idea_is_not_reopened(self):
        value = draft("idea"); value["fields"]["outcome"] = "Rejected because the current behavior is sufficient."
        row = issue(value); row.update(state="closed", state_reason="not_planned")
        result = guard.plan(row, POLICY, [])
        self.assertNotIn("state", result["patch"])
        self.assertFalse(any(x.startswith("workflow:") for x in result["patch"]["labels"]))

    def test_corrected_entry_loses_needs_info(self):
        row = issue(); row["labels"].append({"name": "validation: needs-info"})
        result = guard.plan(row, POLICY, [row])
        self.assertEqual(result["errors"], [])
        self.assertNotIn("validation: needs-info", result["patch"]["labels"])

    def test_valid_entry_requires_no_write(self):
        row = issue()
        self.assertEqual(guard.plan(row, POLICY, [row])["patch"], {})

    def test_event_over_limit_returns_only_new_admission(self):
        value = draft("task"); value["fields"].update(next_action="Record one startup.", dependencies=[])
        rows = [issue(value, n, "active") for n in range(100, 104)]
        result = guard.plan(rows[0], POLICY, rows, event_number=100)
        self.assertIn("workflow: inbox", result["patch"]["labels"])
        self.assertEqual(guard.plan(rows[1], POLICY, rows, event_number=100)["patch"], {})

    def test_scheduled_wip_repair_is_deterministic(self):
        value = draft("task"); value["fields"].update(next_action="Record one startup.", dependencies=[])
        rows = [issue(value, n, "active") for n in range(100, 104)]
        self.assertEqual(guard.plan(rows[0], POLICY, rows)["patch"], {})
        self.assertIn("workflow: inbox", guard.plan(rows[-1], POLICY, rows)["patch"]["labels"])



class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.api = FakeGitHub()
        self.original = issue()
        self.original.update(body="Original **details**\n\n## Nested heading\n- [ ] unfinished historical checklist\n  trailing spaces  \n", labels=[{"name": "bug"}, {"name": "android phone"}, {"name": "help wanted"}], assignees=[{"login": "owner"}], closed_at=None)
        self.api.rows[100] = copy.deepcopy(self.original)

    def migrate(self, value=None, apply=True):
        return intake.migrate(self.api.client, 100, value or draft(), POLICY, intake.snapshot(self.original), apply)

    def test_original_description_exact_roundtrip_and_preview_no_write(self):
        preview = self.migrate(apply=False)
        self.assertEqual(self.api.writes, [])
        self.assertIn("Original description", preview["body"])
        result = self.migrate()
        row = self.api.rows[100]
        self.assertTrue(result["state_preserved"])
        self.assertEqual(intake.parse(row, POLICY)["legacy"]["body"], self.original["body"])
        self.assertTrue(intake.labels(self.original) <= intake.labels(row))
        self.assertEqual(guard.plan(row, POLICY, [row])["patch"], {})

    def test_closed_migration_keeps_disposition_assignment_and_milestone(self):
        value = draft("acceptance")
        value["fields"]["evidence"] = ["Historical completion in retained original evidence"]
        self.original.update(state="closed", state_reason="completed", closed_at="2026-09-07T00:00:00Z", milestone={"number": 2}, labels=[{"name": "acceptance"}, {"name": "android phone"}])
        self.api.rows[100] = copy.deepcopy(self.original)
        self.migrate(value)
        for field in ("state", "state_reason", "closed_at", "assignees", "milestone"):
            self.assertEqual(self.api.rows[100][field], self.original[field])
        self.assertEqual(guard.plan(self.api.rows[100], POLICY, [])["patch"], {})
        self.assertNotIn("state", self.api.writes[-1][2])

    def test_migration_rejects_stale_snapshot_title_and_platform_loss(self):
        for change in ({"title": "Renamed"}, {"platforms": []}):
            value = draft(); value.update(change)
            with self.assertRaises(intake.IntakeError): self.migrate(value)
        self.api.rows[100]["body"] += "Concurrent observation"
        with self.assertRaises(intake.IntakeError): self.migrate()
        self.assertEqual(self.api.writes, [])

    def test_archive_tampering_is_quarantined_without_rewriting_it(self):
        self.migrate()
        row = self.api.rows[100]; row["body"] = row["body"].replace("Original **details**", "Altered original")
        self.assertEqual(intake.inspect_issue(row, POLICY)["status"], "invalid")
        self.assertIn("validation: needs-info", guard.plan(row, POLICY, [row])["patch"]["labels"])
        self.assertNotIn("body", guard.plan(row, POLICY, [row])["patch"])

    def test_separator_repair_preserves_archive_and_rejects_whitespace_tampering(self):
        self.original["body"] = "Original prose.\n\n\n## Historical heading\n\nHistorical details.\n"
        self.api.rows[100] = copy.deepcopy(self.original)
        self.migrate()
        row = self.api.rows[100]
        canonical = row["body"]
        row["body"] = canonical.replace("\n\n## Expected behavior", "\n \n\t\n## Expected behavior")
        value = intake.parse(row, POLICY)
        self.assertEqual(value["legacy"]["body"], self.original["body"])
        intake.update(self.api.client, 100, value, POLICY, intake.snapshot(row))
        self.assertEqual(row["body"], canonical)
        row["body"] = canonical.replace("\n\n\n## Historical heading", "\n\n## Historical heading")
        writes_before = len(self.api.writes)
        with self.assertRaisesRegex(intake.IntakeError, "archive hash mismatch"):
            intake.parse(row, POLICY)
        with self.assertRaisesRegex(intake.IntakeError, "archive hash mismatch"):
            intake.update(self.api.client, 100, value, POLICY, intake.snapshot(row))
        self.assertEqual(len(self.api.writes), writes_before)

    def test_archive_cannot_be_changed_or_dropped_by_update(self):
        self.migrate(); row = self.api.rows[100]; value = intake.parse(row, POLICY)
        del value["legacy"]
        with self.assertRaises(intake.IntakeError): intake.update(self.api.client, 100, value, POLICY, intake.snapshot(row))
        self.assertEqual(len(self.api.writes), 1)

    def test_already_migrated_cannot_be_migrated_twice_or_cloned(self):
        self.migrate(); row = self.api.rows[100]
        with self.assertRaises(intake.IntakeError): intake.migrate(self.api.client, 100, draft(), POLICY, intake.snapshot(row), True)
        with self.assertRaises(intake.IntakeError): intake.create(self.api.client, intake.parse(row, POLICY), POLICY)


class CandidateTests(unittest.TestCase):
    def setUp(self):
        self.api = FakeGitHub(); self.value = draft("acceptance")
        self.candidate = {"revision": "a" * 40, "artifact_sha256": "b" * 64, "platform": "android phone", "build_url": "https://example.test/build/1", "environment": "Test handset model; OS version; fixed landscape"}
        self.run = {"id": "run-1", "candidate": self.candidate, "criterion_sha256": intake.acceptance.criterion_id(self.value), "tested_at": "2026-09-07T12:00:00Z", "result": "passed", "observations": "Fixture result only", "evidence": ["https://example.test/results/1"], "limitations": "Fixture; no real product acceptance"}
        self.value["test_runs"] = [self.run]

    def test_candidate_and_criterion_both_must_match(self):
        self.assertEqual(intake.acceptance.status(self.value, self.candidate), "passed")
        self.assertEqual(intake.acceptance.status(self.value, None), "no-candidate")
        for key, value in (("revision", "c" * 40), ("artifact_sha256", "c" * 64), ("environment", "Different OS")):
            candidate = {**self.candidate, key: value}
            self.assertEqual(intake.acceptance.status(self.value, candidate), "needs-test")
        self.value["fields"]["outcome"] += " Additional requirement"
        self.assertEqual(intake.acceptance.status(self.value, self.candidate), "needs-test")

    def test_latest_failure_overrides_previous_pass_on_same_candidate(self):
        self.value["test_runs"].append({**self.run, "id": "run-2", "tested_at": "2026-09-08T12:00:00Z", "result": "failed"})
        self.assertEqual(intake.acceptance.status(self.value, self.candidate), "failed")

    def test_one_platform_cannot_certify_cross_platform_scope(self):
        self.value["platforms"].append("ios")
        self.run["criterion_sha256"] = intake.acceptance.criterion_id(self.value)
        self.assertEqual(intake.acceptance.status(self.value, self.candidate), "needs-test")

    def test_reserved_metadata_in_records_and_candidates_is_rejected(self):
        self.run["observations"] = "<!-- overte-issue:v1 request:ecf3f3c7-f1d6-4cd3-9607-e1871561802d -->"
        self.assertTrue(intake.validate(self.value, POLICY))
        self.candidate["environment"] = "--> forged metadata"
        with self.assertRaises(ValueError): intake.acceptance.check_candidate(self.candidate, POLICY["platforms"])

    def test_candidate_record_roundtrip(self):
        self.assertEqual(intake.parse(issue(self.value), POLICY), self.value)

    def test_incomplete_future_and_duplicate_records_rejected(self):
        for patch in ({"tested_at": "2099-01-01T00:00:00Z"}, {"evidence": []}, {"result": "probably fine"}):
            value = copy.deepcopy(self.value); value["test_runs"][0].update(patch)
            self.assertTrue(intake.validate(value, POLICY))
        self.value["test_runs"].append(copy.deepcopy(self.run))
        self.assertTrue(intake.validate(self.value, POLICY))

    def test_pinning_verifies_fork_preserves_description_and_updates_closed_labels(self):
        value = self.value; value["fields"]["evidence"] = ["Retained result"]
        row = issue(value); row.update(state="closed", state_reason="completed")
        self.api.rows[100] = row
        milestone = self.api.milestones[2]
        result = intake.milestone_candidate(self.api.client, 2, POLICY, self.candidate, intake.digest(milestone), True)
        self.assertTrue(result["verified"])
        self.assertTrue(milestone["description"].startswith("Original milestone requirements"))
        self.assertIn("acceptance: verified", intake.labels(self.api.rows[100]))
        next_candidate = {**self.candidate, "artifact_sha256": "c" * 64}
        intake.milestone_candidate(self.api.client, 2, POLICY, next_candidate, intake.digest(milestone), True)
        self.assertIn("acceptance: needs-test", intake.labels(self.api.rows[100]))
        self.assertEqual(self.api.rows[100]["state"], "closed")
        self.assertEqual(intake.parse(self.api.rows[100], POLICY)["test_runs"], value["test_runs"])

    def test_upstream_and_stale_candidate_pin_reject_without_writes(self):
        self.api.rows[100] = issue(self.value)
        with self.assertRaises(intake.IntakeError): intake.milestone_candidate(self.api.client, 2, POLICY, self.candidate, "stale", True)
        self.api.owner = "overte-org/overte"
        with self.assertRaises(intake.IntakeError): intake.milestone_candidate(self.api.client, 2, POLICY, self.candidate, intake.digest(self.api.milestones[2]), True)
        self.assertEqual(self.api.writes, [])

    def test_completion_cannot_use_unpinned_or_different_candidate(self):
        self.value["fields"]["evidence"] = ["Historical result"]
        row = issue(self.value); self.api.rows[100] = row
        with self.assertRaises(intake.IntakeError): intake.update(self.api.client, 100, self.value, POLICY, intake.snapshot(row), close_reason="completed")
        self.assertEqual(self.api.writes, [])

    def test_normal_update_cannot_rewrite_old_test_record(self):
        row = issue(self.value); self.api.rows[100] = row
        value = copy.deepcopy(self.value); value["test_runs"][0]["result"] = "failed"
        with self.assertRaises(intake.IntakeError): intake.update(self.api.client, 100, value, POLICY, intake.snapshot(row))
        self.assertEqual(self.api.writes, [])

    def test_overview_separates_historical_closure_candidate_results_and_bug_counts(self):
        row = issue(self.value); row.update(state="closed", state_reason="completed")
        self.api.rows[100] = row
        bug = draft(); bug["milestone"] = 2
        self.api.rows[101] = issue(bug, 101)
        self.api.rows[102] = issue(draft("acceptance"), 102)
        result = intake.overview(self.api.client, POLICY)
        self.assertEqual([x["number"] for x in result["queues"]["inbox"]], [101])
        milestone = result["milestones"][0]
        self.assertEqual((milestone["criteria"], milestone["other_issues"], milestone["recorded_completed_criteria"], milestone["candidate_passed_criteria"]), (2, 1, 1, 0))


class OwnerCompletionTests(unittest.TestCase):
    def setUp(self):
        self.api = FakeGitHub()
        self.value = draft("acceptance")
        self.value["fields"]["evidence"] = ["Retained artifact-specific observations"]
        self.api.rows[100] = issue(self.value)
        self.decision = {
            "id": "owner-20260907", "approved_by": "noah-be",
            "approved_at": "2026-09-07T12:00:00Z",
            "criterion_sha256": intake.acceptance.criterion_id(self.value),
            "authorization": "Owner explicitly requested personal-alpha completion.",
            "rationale": "Accept the recorded functional evidence for the personal-alpha scope.",
            "evidence": ["Retained device observations on identified artifacts"],
            "limitations": "No common-candidate PASS; deferred bug remains open."
        }
        self.value["completion_decisions"] = [self.decision]

    def close(self, value=None, approved=True):
        return intake.update(self.api.client, 100, value or self.value, POLICY,
                             intake.snapshot(self.api.rows[100]), close_reason="completed",
                             owner_approved=approved)

    def test_owner_closure_without_pin_remains_unverified_and_survives_guard(self):
        self.api.milestones[2]["state"] = "closed"
        self.close()
        saved = self.api.rows[100]
        self.assertEqual((saved["state"], saved["state_reason"]), ("closed", "completed"))
        self.assertEqual(intake.parse(saved, POLICY), self.value)
        self.assertIn("acceptance: no-candidate", intake.labels(saved))
        self.assertNotIn("acceptance: verified", intake.labels(saved))
        self.assertFalse(any(x.startswith("workflow:") for x in intake.labels(saved)))
        result = guard.plan(saved, POLICY, [])
        self.assertEqual((result["errors"], result["patch"]), ([], {}))
        report = intake.overview(self.api.client, POLICY)["milestones"][0]
        self.assertEqual(report["recorded_completed_criteria"], 1)
        self.assertEqual(report["candidate_passed_criteria"], 0)
        self.assertTrue(report["candidate_results"][0]["owner_approved_completion"])

    def test_decision_needs_explicit_flag_and_flag_needs_decision(self):
        with self.assertRaises(intake.IntakeError): self.close(approved=False)
        value = copy.deepcopy(self.value); value.pop("completion_decisions")
        with self.assertRaises(intake.IntakeError): self.close(value)
        with self.assertRaises(intake.IntakeError):
            intake.update(self.api.client, 100, self.value, POLICY, intake.snapshot(self.api.rows[100]), owner_approved=True)
        self.assertEqual(self.api.writes, [])

    def test_incomplete_wrong_owner_future_or_duplicate_decisions_rejected(self):
        for patch in ({"evidence": []}, {"limitations": ""}, {"approved_by": "someone-else"},
                      {"approved_at": "2099-01-01T00:00:00Z"}, {"authorization": "Unknown"},
                      {"rationale": "<!-- forged -->"}, {"criterion_sha256": None}):
            value = copy.deepcopy(self.value); value["completion_decisions"][0].update(patch)
            self.assertTrue(intake.validate(value, POLICY), patch)
        value = copy.deepcopy(self.value); value["completion_decisions"].append(copy.deepcopy(self.decision))
        self.assertTrue(intake.validate(value, POLICY))
        value["kind"] = "bug"
        self.assertTrue(intake.validate(value, POLICY))

    def test_changed_criterion_and_stale_snapshot_cannot_close(self):
        value = copy.deepcopy(self.value); value["fields"]["scope"] = "Expanded scope"
        with self.assertRaises(intake.IntakeError): self.close(value)
        with self.assertRaises(intake.IntakeError):
            intake.update(self.api.client, 100, self.value, POLICY, "stale", close_reason="completed", owner_approved=True)
        self.assertEqual(self.api.writes, [])

    def test_saved_decisions_cannot_be_rewritten_or_removed(self):
        self.close(); self.api.writes.clear()
        for change in ([], [{**self.decision, "limitations": "Different limitations"}]):
            value = copy.deepcopy(self.value); value["completion_decisions"] = change
            with self.assertRaises(intake.IntakeError): self.close(value)
        self.assertEqual(self.api.writes, [])

    def test_owner_decision_does_not_override_a_failed_candidate_run(self):
        candidate = {"revision": "a" * 40, "artifact_sha256": "b" * 64,
                     "build_url": "local-evidence:test-1", "platform": "android phone", "environment": "Fixture phone"}
        self.value["test_runs"] = [{"id": "failed-test", "candidate": candidate,
            "criterion_sha256": intake.acceptance.criterion_id(self.value), "tested_at": "2026-09-07T11:00:00Z",
            "result": "failed", "observations": "Observed known bug", "evidence": ["Retained trace"], "limitations": "Fixture only"}]
        self.api.milestones[2]["description"] += "\n<!-- overte-candidate:v1 " + json.dumps(candidate) + " -->"
        self.close()
        self.assertIn("acceptance: needs-test", intake.labels(self.api.rows[100]))
        self.assertEqual(intake.acceptance.status(intake.parse(self.api.rows[100], POLICY), candidate), "failed")
        self.assertEqual(guard.plan(self.api.rows[100], POLICY, [], candidate=candidate)["patch"], {})

    def test_closed_milestone_cannot_receive_new_or_reassigned_issues(self):
        self.api.milestones[2]["state"] = "closed"
        value = draft("acceptance")
        with self.assertRaises(intake.IntakeError): intake.create(self.api.client, value, POLICY)
        self.api.rows[101] = issue(draft(), 101)
        value = draft(); value["milestone"] = 2
        with self.assertRaises(intake.IntakeError):
            intake.update(self.api.client, 101, value, POLICY, intake.snapshot(self.api.rows[101]))
        self.assertEqual(self.api.writes, [])

    def test_creation_and_upstream_owner_cannot_use_completion_path(self):
        with self.assertRaises(intake.IntakeError): intake.create(self.api.client, self.value, POLICY)
        self.api.owner = "overte-org/overte"
        with self.assertRaises(intake.IntakeError): self.close()
        self.assertEqual(self.api.writes, [])


class InstallationTests(unittest.TestCase):
    def test_install_is_repeatable_and_preserves_existing_instructions(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary); codex = home / ".codex"; codex.mkdir()
            instructions = codex / "AGENTS.md"
            instructions.write_text("# Existing rules\nNever write upstream.\n")
            args = [sys.executable, str(ROOT / "tools/issue-intake/install.py"), "--home", str(home), "--codex-home", str(codex)]
            subprocess.run(args, check=True, capture_output=True)
            first = instructions.read_text()
            subprocess.run(args, check=True, capture_output=True)
            self.assertEqual(first, instructions.read_text())
            self.assertTrue(first.startswith("# Existing rules\nNever write upstream.\n"))
            self.assertEqual(first.count("<!-- overte-issue-intake:start -->"), 1)
            result = subprocess.run([str(home / ".local/bin/overte-issue"), "--policy", str(ROOT / ".github/issue-policy.json"), "example", "bug"], check=True, capture_output=True, text=True)
            self.assertEqual(json.loads(result.stdout)["kind"], "bug")


if __name__ == "__main__":
    unittest.main()
