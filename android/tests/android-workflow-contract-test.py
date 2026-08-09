#!/usr/bin/env python3
"""Security and reproducibility contracts for Android Phone Actions workflows."""

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/android-tests.yml"
ACTION_USE = re.compile(r"^\s*(?:-\s+)?uses:\s*([^\s#]+)", re.MULTILINE)
FULL_SHA_ACTION = re.compile(r"^[^@\s]+@[0-9a-f]{40}$")


class AndroidTestWorkflowContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = WORKFLOW.read_text(encoding="utf-8")

    def test_pull_requests_are_untrusted_and_read_only(self):
        self.assertRegex(self.source, r"(?m)^  pull_request:$")
        self.assertNotIn("pull_request_target:", self.source)
        self.assertRegex(self.source, r"(?m)^permissions:\n  contents: read$")
        self.assertNotRegex(self.source, r"(?m)^\s+(?:contents|id-token|packages|actions): write$")

    def test_all_actions_are_pinned_to_immutable_commits(self):
        actions = ACTION_USE.findall(self.source)
        self.assertGreaterEqual(len(actions), 10)
        self.assertEqual(
            [action for action in actions if not FULL_SHA_ACTION.fullmatch(action)],
            [],
            "pin every action to an immutable 40-character commit SHA",
        )

    def test_every_checkout_discards_credentials(self):
        checkouts = self.source.count("uses: actions/checkout@")
        self.assertGreaterEqual(checkouts, 4)
        self.assertEqual(self.source.count("persist-credentials: false"), checkouts)

    def test_runs_are_bounded_and_pull_requests_cancel_superseded_work(self):
        self.assertIn("github.event.pull_request.number || github.ref", self.source)
        self.assertIn("cancel-in-progress: ${{ github.event_name == 'pull_request' }}", self.source)
        timeouts = [int(value) for value in re.findall(r"timeout-minutes:\s*(\d+)", self.source)]
        self.assertGreaterEqual(len(timeouts), 4)
        self.assertLessEqual(max(timeouts), 30)

    def test_reports_are_small_and_short_lived(self):
        retentions = [int(value) for value in re.findall(r"retention-days:\s*(\d+)", self.source)]
        self.assertGreaterEqual(len(retentions), 5)
        self.assertLessEqual(max(retentions), 7)
        self.assertNotRegex(self.source, r"(?im)^\s+.*\.apk\s*$")

    def test_phone_branch_and_ci_work_are_checked(self):
        self.assertIn("feature/android-phone-support", self.source)
        self.assertIn('"ci/android-phone-**"', self.source)
        self.assertIn('"test/android-**"', self.source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
