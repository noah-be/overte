#!/usr/bin/env python3
"""Security and reproducibility contracts for the Pico 4 CI workflow."""

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/project-tests.yml"
ACTION_USE = re.compile(r"^\s*uses:\s*([^\s#]+)", re.MULTILINE)
FULL_SHA_ACTION = re.compile(r"^[^@\s]+@[0-9a-f]{40}$")


class PicoWorkflowContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = WORKFLOW.read_text(encoding="utf-8")

    def test_untrusted_pull_requests_have_read_only_permissions(self):
        self.assertIn("pull_request:", self.source)
        self.assertNotIn("pull_request_target:", self.source)
        self.assertRegex(self.source, r"(?m)^permissions:\n  contents: read$")
        self.assertNotRegex(self.source, r"(?m)^\s*(id-token|packages|actions): write$")

    def test_every_action_is_pinned_to_a_full_commit(self):
        actions = ACTION_USE.findall(self.source)
        self.assertGreaterEqual(len(actions), 5)
        self.assertEqual(
            [action for action in actions if not FULL_SHA_ACTION.fullmatch(action)],
            [],
            "pin every action to an immutable 40-character commit SHA",
        )

    def test_checkout_does_not_persist_credentials(self):
        self.assertIn("persist-credentials: false", self.source)

    def test_duplicate_runs_are_cancelled_and_jobs_are_bounded(self):
        self.assertIn("cancel-in-progress: true", self.source)
        timeout = re.search(r"(?m)^\s+timeout-minutes:\s*(\d+)\s*$", self.source)
        self.assertIsNotNone(timeout)
        self.assertLessEqual(int(timeout.group(1)), 30)

    def test_reports_have_short_explicit_retention(self):
        retention = re.search(r"(?m)^\s+retention-days:\s*(\d+)\s*$", self.source)
        self.assertIsNotNone(retention)
        self.assertLessEqual(int(retention.group(1)), 7)
        self.assertNotIn("*.apk", self.source.lower())

    def test_ci_uses_the_repository_entry_point(self):
        self.assertIn("tests/run-project-tests.py", self.source)
        self.assertIn("--junit build/test-results/project-tests.xml", self.source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
