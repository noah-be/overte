#!/usr/bin/env python3
"""Offline maintenance behavior using temporary Git repositories and snapshots."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("repository_maintenance", ROOT / "tools/repository-maintenance/check.py")
MAINTENANCE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MAINTENANCE)
NOW = datetime(2026, 9, 24, 12, tzinfo=timezone.utc)
SHA = "1" * 40
ISSUE_POLICY = json.loads((ROOT / ".github/issue-policy.json").read_text())


def freshness():
    return {"schema": 2, "repository": MAINTENANCE.REPOSITORY, "mode": "freshness", "status": "FRESH",
            "generated_at": NOW.isoformat(), "last_complete_at": (NOW - timedelta(hours=1)).isoformat(),
            "last_complete_status": "PASS", "source_sha": SHA}


class EvidenceTests(unittest.TestCase):
    def test_absent_local_deferred_and_legacy_evidence_never_implies_live_pass(self):
        for document, expected in ((None, "UNKNOWN"), ({"schema": 1}, "UNKNOWN"),
                                    ({"schema": 2, "mode": "local", "status": "PASS", "generated_at": NOW.isoformat()}, "LOCAL_ONLY"),
                                    ({"schema": 2, "mode": "live", "status": "DEFERRED_PROPAGATION",
                                      "generated_at": NOW.isoformat(), "admission": {}}, "UNKNOWN")):
            self.assertEqual(MAINTENANCE.health_snapshot(document, NOW, 30, {"main": SHA})["status"], expected)

    def test_fresh_failed_old_future_and_wrong_source_reports_stay_distinct(self):
        report = freshness()
        self.assertEqual(MAINTENANCE.health_snapshot(report, NOW, 30, {"main": SHA})["status"], "REPORTED_PASS")
        report["last_complete_status"] = "FAIL"
        self.assertEqual(MAINTENANCE.health_snapshot(report, NOW, 30, {"main": SHA})["status"], "REPORTED_FAIL")
        report["last_complete_at"] = (NOW - timedelta(hours=31)).isoformat()
        self.assertEqual(MAINTENANCE.health_snapshot(report, NOW, 30, {"main": SHA})["status"], "STALE")
        self.assertEqual(MAINTENANCE.health_snapshot(freshness(), NOW, 30, {"main": "2" * 40})["status"], "STALE_SOURCE")
        report["last_complete_at"] = (NOW + timedelta(hours=1)).isoformat()
        with self.assertRaises(ValueError):
            MAINTENANCE.health_snapshot(report, NOW, 30, {"main": SHA})

    def test_inconsistent_and_null_live_evidence_is_rejected(self):
        report = {"schema": 2, "mode": "live", "generated_at": NOW.isoformat(), "status": "PASS",
                  "audit_complete": True, "audit_executed": True, "admission": None}
        with self.assertRaises(ValueError):
            MAINTENANCE.health_snapshot(report, NOW, 30, {"main": SHA})
        report["admission"] = {"accepted": True}
        with self.assertRaises(ValueError):
            MAINTENANCE.health_snapshot(report, NOW, 30, {"main": SHA})

    def test_issue_states_use_policy_limits_and_only_suggest_review(self):
        issues = [{"number": index, "state": "open", "labels": ["workflow: active"],
                   "updated_at": (NOW - timedelta(days=15)).isoformat()} for index in range(1, 5)]
        document = {"schema": 1, "complete": True, "generated_at": NOW.isoformat(), "issues": issues}
        result = MAINTENANCE.issue_snapshot(document, NOW, ISSUE_POLICY)
        self.assertEqual(result["over_limit"], {"active": 4})
        self.assertEqual(result["review_active"], [1, 2, 3, 4])
        self.assertEqual(result["status"], "ATTENTION")
        self.assertEqual(issues[0]["state"], "open")
        document["complete"] = False
        self.assertEqual(MAINTENANCE.issue_snapshot(document, NOW, ISSUE_POLICY)["status"], "UNKNOWN")

    def test_malformed_issue_items_states_and_labels_are_rejected(self):
        for item in (None, {"number": 1, "state": "mystery"},
                     {"number": 1, "state": "open", "labels": [None]}):
            document = {"schema": 1, "complete": True, "generated_at": NOW.isoformat(), "issues": [item]}
            with self.assertRaises(ValueError):
                MAINTENANCE.issue_snapshot(document, NOW, ISSUE_POLICY)

    def test_ten_observations_only_suggest_topology_review(self):
        rows = [{"commit": f"{index:040x}", "maintenance_minutes": 10,
                 "propagation_minutes": 3, "manual_reconciliation": False} for index in range(1, 11)]
        self.assertEqual(MAINTENANCE.propagation_effort({"schema": 1, "changes": rows[:9]})["status"], "OBSERVING")
        result = MAINTENANCE.propagation_effort({"schema": 1, "changes": rows})
        self.assertEqual(result["status"], "REVIEW_TOPOLOGY")
        self.assertEqual(result["authority"], "advisory_only")
        rows[0]["propagation_minutes"] = float("inf")
        with self.assertRaises(ValueError):
            MAINTENANCE.propagation_effort({"schema": 1, "changes": rows})

    def test_snapshot_reader_rejects_foreign_duplicate_and_nonfinite_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "snapshot.json"
            for content in ('{"repository":"overte-org/overte"}',
                            '{"repository":"noah-be/overte","x":1,"x":2}',
                            '{"repository":"noah-be/overte","x":NaN}'):
                path.write_text(content)
                with self.assertRaises(ValueError):
                    MAINTENANCE.read_document(path)


class GitTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="overte-maintenance-fixture-")
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.root = self.directory / "repository"
        self.root.mkdir()
        self.git("init", "-q", "--initial-branch=main")
        self.git("config", "user.name", "Fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        (self.root / ".github").mkdir()
        for name in ("branch-policy.json", "issue-policy.json", "repository-health.json", "branch-cleanup.json"):
            shutil.copyfile(ROOT / ".github" / name, self.root / ".github" / name)
        (self.root / "README.md").write_text("# Fixture\n")
        (self.root / ".gitignore").write_text("build/\n")
        self.git("add", ".")
        self.git("commit", "-qm", "Initial fixture")
        self.base = self.git("rev-parse", "HEAD")
        self.branches = json.loads((self.root / ".github/branch-policy.json").read_text())["branches"]
        for branch in self.branches:
            self.git("update-ref", f"refs/remotes/origin/{branch}", self.base)

    def git(self, *args, root=None):
        return subprocess.check_output(["git", "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null",
                                        *args], cwd=root or self.root, text=True, stderr=subprocess.PIPE).strip()

    def add_worktree(self, branch):
        path = self.directory / branch.replace("/", "-")
        self.git("worktree", "add", "-qb", branch, str(path), self.base)
        return path

    def inventory(self):
        return MAINTENANCE.snapshot(self.root, "refs/remotes/origin", now=NOW)

    def test_offline_inspection_leaves_refs_worktrees_and_index_unchanged(self):
        before = (self.git("show-ref"), self.git("worktree", "list", "--porcelain"), self.git("status", "--porcelain"))
        report = self.inventory()
        after = (self.git("show-ref"), self.git("worktree", "list", "--porcelain"), self.git("status", "--porcelain"))
        self.assertEqual(before, after)
        self.assertEqual(report["remote_state"], "NOT_VERIFIED")
        self.assertEqual(report["health"]["status"], "UNKNOWN")
        self.assertEqual(report["worktrees"]["items"][0]["status"], "RETAIN")
        self.assertTrue(all(edge["status"] == "IN_SYNC" for edge in report["branches"]["edges"]))

    def test_drift_counts_and_missing_refs_remain_visible(self):
        (self.root / "README.md").write_text("# New parent\n")
        self.git("commit", "-qam", "Advance parent")
        self.git("update-ref", "refs/remotes/origin/main", self.git("rev-parse", "HEAD"))
        report = self.inventory()
        drifting = [edge for edge in report["branches"]["edges"] if edge["status"] == "DRIFT"]
        self.assertEqual(len(drifting), 2)
        self.assertTrue(all(edge["missing_parent_commits"] == 1 for edge in drifting))
        self.git("update-ref", "-d", "refs/remotes/origin/apple-main")
        self.assertTrue(any(edge["status"] == "UNKNOWN" for edge in self.inventory()["branches"]["edges"]))

    def test_only_clean_fully_integrated_topic_is_listed_for_review(self):
        clean = self.add_worktree("fix/main/integrated")
        dirty = self.add_worktree("fix/main/dirty")
        (dirty / "unpublished.txt").write_text("unfinished\n")
        locked = self.add_worktree("fix/main/locked")
        self.git("worktree", "lock", "--reason", "retain for recovery", str(locked))
        topic = self.add_worktree("fix/main/unfinished")
        (topic / "README.md").write_text("# Unintegrated\n")
        self.git("commit", "-qam", "Unintegrated", root=topic)
        experiment = self.add_worktree("experiment/main/example")
        rows = {row["path"]: row for row in self.inventory()["worktrees"]["items"]}
        self.assertEqual(rows[str(clean)]["status"], "REVIEW_INTEGRATED")
        self.assertEqual(rows[str(clean)]["remote_holds"], "NOT_CHECKED")
        for path, reason in ((dirty, "uncommitted_work"), (locked, "locked_for_retention"),
                             (topic, "not_fully_integrated"), (experiment, "unmanaged_or_detached_work")):
            self.assertEqual(rows[str(path)]["status"], "RETAIN")
            self.assertIn(reason, rows[str(path)]["reasons"])

    def test_explicit_local_hold_overrides_integration(self):
        topic = self.add_worktree("fix/main/held")
        policy = self.root / ".github/branch-cleanup.json"
        config = json.loads(policy.read_text())
        config["holds"]["fix/main/held"] = "Ongoing work"
        policy.write_text(json.dumps(config))
        row = next(row for row in self.inventory()["worktrees"]["items"] if row["path"] == str(topic))
        self.assertEqual(row["status"], "RETAIN")
        self.assertIn("explicit_policy_hold", row["reasons"])

    def test_missing_registration_is_reported_without_pruning(self):
        topic = self.add_worktree("fix/main/missing")
        shutil.rmtree(topic)
        report = self.inventory()
        row = next(row for row in report["worktrees"]["items"] if row["path"] == str(topic))
        self.assertIn("missing_path_review", row["reasons"])
        self.assertIn(str(topic), self.git("worktree", "list", "--porcelain"))

    def test_symlinked_worktree_is_retained(self):
        topic = self.add_worktree("fix/main/symlinked")
        moved = self.directory / "preserved-worktree"
        topic.rename(moved)
        topic.symlink_to(moved, target_is_directory=True)
        row = next(row for row in self.inventory()["worktrees"]["items"] if row["path"] == str(topic))
        self.assertEqual(row["status"], "RETAIN")
        self.assertIn("symlinked_worktree_review", row["reasons"])

    def test_dirty_submodule_is_uncommitted_work(self):
        component = self.directory / "component"
        component.mkdir()
        self.git("init", "-q", "--initial-branch=main", root=component)
        self.git("config", "user.name", "Fixture", root=component)
        self.git("config", "user.email", "fixture@example.invalid", root=component)
        (component / "source.txt").write_text("committed\n")
        self.git("add", ".", root=component)
        self.git("commit", "-qm", "Component", root=component)
        self.git("-c", "protocol.file.allow=always", "submodule", "add", "-q", str(component), "component")
        self.git("commit", "-qm", "Add component")
        self.base = self.git("rev-parse", "HEAD")
        for branch in self.branches:
            self.git("update-ref", f"refs/remotes/origin/{branch}", self.base)
        topic = self.add_worktree("fix/main/submodule")
        self.git("-c", "protocol.file.allow=always", "submodule", "update", "--init", root=topic)
        (topic / "component/source.txt").write_text("unpublished submodule work\n")
        row = next(row for row in self.inventory()["worktrees"]["items"] if row["path"] == str(topic))
        self.assertEqual(row["status"], "RETAIN")
        self.assertTrue(row["dirty"])
        self.assertIn("uncommitted_work", row["reasons"])

    def test_report_refuses_source_input_symlink_and_git_metadata_overwrite(self):
        path = self.directory / "input.json"
        path.write_text('{"repository":"noah-be/overte"}')
        link = self.directory / "link.json"
        link.symlink_to(path)
        for target, inputs in ((self.root / "README.md", []), (self.root / ".git/config", []),
                               (link, []), (path, [path]), (path, [])):
            with self.subTest(target=target), self.assertRaises(ValueError):
                MAINTENANCE.report_target(self.root, target, inputs)
        self.assertEqual((self.root / "README.md").read_text(), "# Fixture\n")

    def test_cli_unknown_snapshot_and_strict_mode_are_explicit(self):
        target = self.directory / "report.json"
        command = [sys.executable, str(ROOT / "tools/repository-maintenance/check.py"), "status",
                   "--root", str(self.root), "--report", str(target), "--max-actions", "1"]
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Remote state is not verified", result.stdout)
        self.assertIn("additional actions", result.stdout)
        self.assertEqual(json.loads(target.read_text())["remote_state"], "NOT_VERIFIED")
        strict = subprocess.run(command + ["--strict"], capture_output=True, text=True)
        self.assertEqual(strict.returncode, 1, strict.stderr)


if __name__ == "__main__":
    unittest.main()
