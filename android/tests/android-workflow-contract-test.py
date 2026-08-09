#!/usr/bin/env python3
"""Security and reproducibility contracts for Android Phone Actions workflows."""

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/android-tests.yml"
BUILD_WORKFLOW = ROOT / ".github/workflows/android-phone-build.yml"
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


class AndroidPhoneBuildWorkflowContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = BUILD_WORKFLOW.read_text(encoding="utf-8")

    def test_build_is_manual_read_only_and_not_a_pull_request_target(self):
        self.assertRegex(self.source, r"(?m)^  workflow_dispatch:$")
        self.assertNotRegex(self.source, r"(?m)^  (?:pull_request|pull_request_target|push):$")
        self.assertRegex(self.source, r"(?m)^permissions:\n  contents: read$")

    def test_build_uses_dedicated_bounded_self_hosted_runner(self):
        self.assertIn("runs-on: [self-hosted, linux, x64, overte-android-phone-build]", self.source)
        self.assertIn("timeout-minutes: 240", self.source)
        self.assertIn("cancel-in-progress: false", self.source)

    def test_build_accepts_only_reviewed_branch_or_immutable_release_tags(self):
        self.assertIn("Reject untrusted build refs", self.source)
        self.assertIn("refs/heads/feature/android-phone-support", self.source)
        self.assertIn("refs/tags/android-phone-v[0-9]+", self.source)

    def test_build_is_clean_reproducible_and_fail_closed(self):
        self.assertIn("CONAN_HOME: ${{ github.workspace }}/build/ci-phone-conan2", self.source)
        self.assertIn("tests/run-tests.sh host", self.source)
        self.assertIn("./build-phone.sh deps --download", self.source)
        self.assertIn("./build-phone.sh prepare", self.source)
        self.assertIn("./build-phone.sh build --stacktrace", self.source)
        self.assertIn("verify-phone-apk.py", self.source)
        self.assertIn('--source-revision "$GITHUB_SHA"', self.source)
        self.assertIn("--expect-debuggable 1", self.source)

    def test_build_actions_are_immutable_and_checkout_is_credential_free(self):
        actions = ACTION_USE.findall(self.source)
        self.assertGreaterEqual(len(actions), 2)
        self.assertEqual([action for action in actions if not FULL_SHA_ACTION.fullmatch(action)], [])
        self.assertIn("persist-credentials: false", self.source)

    def test_large_apk_is_not_uploaded_as_actions_artifact(self):
        upload = self.source.split("uses: actions/upload-artifact@", 1)[1]
        self.assertNotRegex(upload, r"(?i)\.apk(?:\s|$)")
        self.assertIn("apk-manifest.json", upload)
        self.assertIn("retention-days: 7", upload)


if __name__ == "__main__":
    unittest.main(verbosity=2)
