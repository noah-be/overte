#!/usr/bin/env python3
"""Security and reproducibility contracts for the Pico 4 CI workflow."""

import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/project-tests.yml"
BUILD_WORKFLOW = ROOT / ".github/workflows/pico4-build.yml"
RELEASE_WORKFLOW = ROOT / ".github/workflows/pico4-release-candidate.yml"
DEVICE_WORKFLOW = ROOT / ".github/workflows/pico4-device-acceptance.yml"
ANDROID_TESTS_WORKFLOW = ROOT / ".github/workflows/android-tests.yml"
DOCUMENTATION_WORKFLOW = ROOT / ".github/workflows/documentation-checks.yml"
BRANCH_POLICY_WORKFLOW = ROOT / ".github/workflows/branch-policy.yml"
BRANCH_SYNC_WORKFLOW = ROOT / ".github/workflows/branch-sync.yml"
DESKTOP_TOPOLOGY_WORKFLOW = ROOT / ".github/workflows/desktop-branch-topology.yml"
IOS_WORKFLOW = ROOT / ".github/workflows/ios-bootstrap.yml"
MACOS_WORKFLOW = ROOT / ".github/workflows/macos-bootstrap.yml"
RULESETS = ROOT / ".github/rulesets"
RULESET_FILES = {
    "Android target branch topology": "android-target-branches.json",
    "Apple target branch topology": "apple-target-branches.json",
    "Archived branches": "archived-branches.json",
    "Desktop branch topology": "desktop-branches.json",
    "Immutable Android, canonical, and archive tags": "android-release-tags.json",
    "Immutable Pico 4 release and dependency tags": "pico4-release-tags.json",
    "Permanent branch governance": "permanent-branches.json",
}
ACTION_USE = re.compile(r"^\s*uses:\s*([^\s#]+)", re.MULTILINE)
FULL_SHA_ACTION = re.compile(r"^[^@\s]+@[0-9a-f]{40}$")


class LightweightWorkflowContracts(unittest.TestCase):
    def test_documentation_changes_use_lightweight_checks(self):
        documentation = DOCUMENTATION_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn('"**/*.md"', documentation)
        self.assertIn("tests/check-documentation.py", documentation)
        self.assertIn("timeout-minutes: 5", documentation)
        self.assertIn("persist-credentials: false", documentation)

    def test_app_test_workflows_exclude_markdown(self):
        for workflow in (ANDROID_TESTS_WORKFLOW, WORKFLOW):
            self.assertIn('"!**/*.md"', workflow.read_text(encoding="utf-8"))
        for workflow in (IOS_WORKFLOW, MACOS_WORKFLOW):
            if workflow.exists():
                self.assertIn("'!**/*.md'", workflow.read_text(encoding="utf-8"))


class BranchGovernanceWorkflowContracts(unittest.TestCase):
    def test_policy_is_a_native_read_only_pull_request_check(self):
        source = BRANCH_POLICY_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("pull_request:", source)
        self.assertNotIn("pull_request_target:", source)
        self.assertIn("ref: ${{ github.event.repository.default_branch }}", source)
        self.assertIn("persist-credentials: false", source)
        self.assertRegex(
            source,
            r"(?m)^permissions:\n  contents: read\n  pull-requests: read$",
        )
        self.assertIn("name: branch-policy", source)
        self.assertIn("github.event.pull_request.head.sha", source)
        self.assertIn("github.event.pull_request.head.repo.id", source)
        self.assertIn("github.event.pull_request.base.repo.id", source)
        self.assertIn("github.event.repository.id", source)
        self.assertNotIn("check-runs", source)
        self.assertNotRegex(source, r"(?m)^\s*(checks|pull-requests|contents): write$")

    def test_policy_never_executes_pull_request_policy_or_workflow_changes(self):
        source = BRANCH_POLICY_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("Check out trusted policy", source)
        self.assertIn("github.event.repository.default_branch", source)
        checkout = source.split("with:", 1)[1].split("- name: Validate", 1)[0]
        self.assertNotIn("github.event.pull_request.head.sha", checkout)
        self.assertIn("pulls/$PULL_REQUEST/files", source)
        self.assertIn("gh api --paginate", source)
        self.assertIn("--jq '.[].filename'", source)
        self.assertNotIn("--paginate --slurp", source)
        self.assertIn("--changed-files-stdin", source)

    def test_governance_actions_are_pinned(self):
        for workflow in (BRANCH_POLICY_WORKFLOW, BRANCH_SYNC_WORKFLOW):
            actions = ACTION_USE.findall(workflow.read_text(encoding="utf-8"))
            self.assertGreaterEqual(len(actions), 1)
            self.assertEqual([action for action in actions if not FULL_SHA_ACTION.fullmatch(action)], [])

    def test_sync_is_read_only_drift_detection(self):
        source = BRANCH_SYNC_WORKFLOW.read_text(encoding="utf-8")
        self.assertRegex(source, r"(?m)^permissions:\n  contents: read$")
        self.assertIn("tools/branch-policy/drift.py", source)
        self.assertIn("--expected-parent-sha \"$PUSH_SHA\"", source)
        self.assertIn("github.event.repository.default_branch", source)
        self.assertIn("GITHUB_TOKEN: ${{ github.token }}", source)
        self.assertNotIn("actions/create-github-app-token@", source)
        self.assertNotIn("BRANCH_SYNC_APP", source)
        self.assertNotIn("secrets.", source)
        self.assertNotIn("gh pr", source)
        self.assertNotIn("--auto", source)
        self.assertNotIn("check-runs", source)
        self.assertIn("group: branch-synchronization-${{ github.ref_name }}", source)
        self.assertIn("cancel-in-progress: false", source)
        self.assertNotIn("Skipping $parent -> $child", source)
        self.assertNotIn("continue", source)

    def test_multiple_prs_cannot_be_selected_or_merged(self):
        source = BRANCH_SYNC_WORKFLOW.read_text(encoding="utf-8")
        for forbidden in ("gh pr list", "gh pr create", "gh pr merge", "pulls?", ".[0]"):
            self.assertNotIn(forbidden, source)

    def test_wrong_app_or_author_cannot_authorize_sync(self):
        source = BRANCH_SYNC_WORKFLOW.read_text(encoding="utf-8")
        for forbidden in ("create-github-app-token", "client-id", "private-key", "author", "login"):
            self.assertNotIn(forbidden, source)

    def test_main_sync_policy_includes_linux_and_windows(self):
        policy = (ROOT / ".github/branch-policy.json").read_text(encoding="utf-8")
        self.assertRegex(
            policy,
            r'"children": \["android-main", "apple-main", "linux-main", "windows-main"\]',
        )

    def test_desktop_topology_uses_trusted_main_policy(self):
        source = DESKTOP_TOPOLOGY_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("linux-main", source)
        self.assertIn("windows-main", source)
        self.assertIn("origin/main:tests/desktop-branch-topology-check.py", source)
        self.assertIn("--main origin/main", source)
        self.assertIn("persist-credentials: false", source)
        self.assertRegex(source, r"(?m)^permissions:\n  contents: read$")
        actions = ACTION_USE.findall(source)
        self.assertGreaterEqual(len(actions), 1)
        self.assertEqual(
            [action for action in actions if not FULL_SHA_ACTION.fullmatch(action)], []
        )

    def test_desktop_ruleset_requires_topology_check(self):
        source = (RULESETS / "desktop-branches.json").read_text(encoding="utf-8")
        for branch in ("refs/heads/linux-main", "refs/heads/windows-main"):
            self.assertIn(branch, source)
        self.assertIn('"context": "Enforce main desktop sync path"', source)


class RulesetManifestContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifests = {
            name: json.loads((RULESETS / filename).read_text(encoding="utf-8"))
            for name, filename in RULESET_FILES.items()
        }

    @staticmethod
    def rule(manifest, rule_type):
        return next(rule for rule in manifest["rules"] if rule["type"] == rule_type)

    def test_all_seven_live_rulesets_are_complete_and_versioned(self):
        versioned = []
        for path in RULESETS.glob("*.json"):
            candidate = json.loads(path.read_text(encoding="utf-8"))
            if "target" in candidate:
                versioned.append(path.name)

        self.assertEqual(sorted(versioned), sorted(RULESET_FILES.values()))
        self.assertEqual(set(self.manifests), set(RULESET_FILES))
        for name, manifest in self.manifests.items():
            self.assertEqual(manifest["name"], name)
            self.assertIn(manifest["target"], ("branch", "tag"))
            self.assertEqual(manifest["enforcement"], "active")
            self.assertEqual(manifest["bypass_actors"], [])
            self.assertEqual(manifest["conditions"]["ref_name"]["exclude"], [])
            self.assertTrue(manifest["conditions"]["ref_name"]["include"])
            self.assertTrue(manifest["rules"])

    def test_required_checks_are_strict_and_bound_to_github_actions(self):
        expected = {
            "Android target branch topology": "Enforce Android parent sync path",
            "Apple target branch topology": "Enforce apple-main sync path",
            "Desktop branch topology": "Enforce main desktop sync path",
            "Permanent branch governance": "branch-policy",
        }
        for name, context in expected.items():
            parameters = self.rule(
                self.manifests[name], "required_status_checks"
            )["parameters"]
            self.assertTrue(parameters["strict_required_status_checks_policy"])
            self.assertFalse(parameters["do_not_enforce_on_create"])
            self.assertEqual(
                parameters["required_status_checks"],
                [{"context": context, "integration_id": 15368}],
            )

    def test_desktop_workflow_and_manifest_use_identical_check_context(self):
        workflow = DESKTOP_TOPOLOGY_WORKFLOW.read_text(encoding="utf-8")
        actual = re.search(
            r"(?m)^\s{4}name:\s*(Enforce main desktop sync path)\s*$", workflow
        )
        self.assertIsNotNone(actual)
        parameters = self.rule(
            self.manifests["Desktop branch topology"], "required_status_checks"
        )["parameters"]
        self.assertEqual(
            parameters["required_status_checks"][0]["context"], actual.group(1)
        )

    def test_solo_profile_is_active_without_locking_out_the_maintainer(self):
        solo = json.loads(
            (RULESETS / "review-profiles/solo-maintainer.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(solo["required_approving_review_count"], 0)
        self.assertFalse(solo["require_last_push_approval"])
        self.assertEqual(solo["allowed_merge_methods"], ["merge"])
        for name in (
            "Android target branch topology",
            "Apple target branch topology",
            "Permanent branch governance",
        ):
            self.assertEqual(
                self.rule(self.manifests[name], "pull_request")["parameters"], solo
            )

    def test_independent_reviewer_profile_is_ready_but_not_active(self):
        independent = json.loads(
            (RULESETS / "review-profiles/independent-reviewer.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(independent["required_approving_review_count"], 1)
        self.assertTrue(independent["dismiss_stale_reviews_on_push"])
        self.assertTrue(independent["require_last_push_approval"])
        self.assertTrue(independent["required_review_thread_resolution"])
        for manifest in self.manifests.values():
            for rule in manifest["rules"]:
                if rule["type"] == "pull_request":
                    self.assertNotEqual(rule["parameters"], independent)

    def test_governed_refs_retain_deletion_and_non_fast_forward_protection(self):
        for name in (
            "Android target branch topology",
            "Apple target branch topology",
            "Archived branches",
            "Immutable Android, canonical, and archive tags",
            "Immutable Pico 4 release and dependency tags",
            "Permanent branch governance",
        ):
            rule_types = {rule["type"] for rule in self.manifests[name]["rules"]}
            self.assertIn("deletion", rule_types)
            self.assertIn("non_fast_forward", rule_types)

    def test_archives_are_immutable(self):
        archived = self.manifests["Archived branches"]
        self.assertEqual(
            archived["conditions"]["ref_name"]["include"],
            [
                "refs/heads/android-vr-quest",
                "refs/heads/apple-macos",
                "refs/heads/backup/**",
            ],
        )
        self.assertEqual(
            self.rule(archived, "update")["parameters"],
            {"update_allows_fetch_and_merge": False},
        )

    def test_used_release_dependency_and_archive_tag_namespaces_are_protected(self):
        protected = set()
        for name, manifest in self.manifests.items():
            if manifest["target"] == "tag":
                protected.update(manifest["conditions"]["ref_name"]["include"])
        self.assertEqual(
            protected,
            {
                "refs/tags/[0-9]*",
                "refs/tags/v[0-9]*",
                "refs/tags/android-phone-v*",
                "refs/tags/android-phone-16k-deps-v*",
                "refs/tags/archive/**",
                "refs/tags/pico4-v*-rc.*",
                "refs/tags/pico4-preview-*",
                "refs/tags/pico4-deps-v*",
            },
        )

    def test_signed_commits_are_not_required(self):
        for manifest in self.manifests.values():
            self.assertNotIn(
                "required_signatures", {rule["type"] for rule in manifest["rules"]}
            )

    def test_repository_merge_settings_match_transition_policy(self):
        settings = json.loads(
            (RULESETS / "repository-merge-settings.json").read_text(encoding="utf-8")
        )
        self.assertEqual(settings["repository"], "noah-be/overte")
        self.assertEqual(
            settings["settings"],
            {
                "allow_auto_merge": False,
                "allow_merge_commit": True,
                "allow_rebase_merge": False,
                "allow_squash_merge": False,
                "allow_update_branch": False,
                "delete_branch_on_merge": False,
            },
        )


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


class PicoBuildWorkflowContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = BUILD_WORKFLOW.read_text(encoding="utf-8")

    def test_build_is_manual_and_cannot_run_untrusted_pull_request_code(self):
        self.assertRegex(self.source, r"(?m)^  workflow_dispatch:$")
        self.assertNotRegex(self.source, r"(?m)^  pull_request(?:_target)?:$")
        self.assertNotRegex(self.source, r"(?m)^  push:$")
        self.assertRegex(self.source, r"(?m)^permissions:\n  contents: read$")

    def test_build_uses_dedicated_self_hosted_runner_and_bounded_job(self):
        self.assertIn("runs-on: [self-hosted, linux, x64, overte-android-build]", self.source)
        self.assertIn("timeout-minutes: 240", self.source)
        self.assertIn("cancel-in-progress: false", self.source)

    def test_build_actions_are_immutable_and_checkout_is_credential_free(self):
        actions = ACTION_USE.findall(self.source)
        self.assertGreaterEqual(len(actions), 2)
        self.assertEqual([action for action in actions if not FULL_SHA_ACTION.fullmatch(action)], [])
        self.assertIn("persist-credentials: false", self.source)

    def test_build_runs_tests_and_fail_closed_apk_verification(self):
        self.assertIn("Reject untrusted build refs", self.source)
        self.assertIn("refs/heads/android-vr-pico", self.source)
        self.assertIn("refs/tags/pico4-preview-[0-9]+", self.source)
        self.assertIn("tests/run-project-tests.py", self.source)
        self.assertIn("./vr/pico/build.sh doctor", self.source)
        self.assertIn("./vr/pico/build.sh deps --download", self.source)
        self.assertIn("./vr/pico/build.sh build --stacktrace", self.source)
        self.assertIn("android/vr/pico/ci/verify-pico-apk.py", self.source)
        self.assertIn('--source-revision "$GITHUB_SHA"', self.source)

    def test_large_apk_is_not_uploaded_to_actions_storage(self):
        upload = self.source.split("uses: actions/upload-artifact@", 1)[1]
        self.assertNotRegex(upload, r"(?i)\.apk(?:\s|$)")
        self.assertIn("apk-manifest.json", upload)
        self.assertIn("retention-days: 7", upload)


class PicoReleaseWorkflowContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = RELEASE_WORKFLOW.read_text(encoding="utf-8")

    def test_release_is_manual_only_and_tag_fail_closed(self):
        self.assertRegex(self.source, r"(?m)^  workflow_dispatch:$")
        self.assertNotRegex(self.source, r"(?m)^  (pull_request|pull_request_target|push):$")
        self.assertIn('[[ "$GITHUB_REF_TYPE" == tag ]]', self.source)
        self.assertIn("pico4-release.py", self.source)
        self.assertNotIn("refs/heads/android-vr-pico", self.source)

    def test_release_has_protected_boundary_and_dedicated_runner(self):
        self.assertIn("environment: pico4-release-candidate", self.source)
        self.assertIn("runs-on: [self-hosted, linux, x64, overte-android-release]", self.source)
        self.assertRegex(self.source, r"(?m)^permissions:\n  contents: read$")
        self.assertIn("contents: write", self.source)

    def test_release_actions_are_pinned_and_checkout_has_no_credentials(self):
        actions = ACTION_USE.findall(self.source)
        self.assertGreaterEqual(len(actions), 2)
        self.assertEqual([action for action in actions if not FULL_SHA_ACTION.fullmatch(action)], [])
        self.assertIn("persist-credentials: false", self.source)

    def test_release_reuses_gates_and_only_creates_a_draft(self):
        for contract in ("tests/run-project-tests.py", "./vr/pico/build.sh deps --download",
                         "android/vr/pico/ci/verify-pico-apk.py", "--expected-version-code",
                         "--expected-version-name", "--expected-signer-sha256"):
            self.assertIn(contract, self.source)
        self.assertIn("gh release create", self.source)
        self.assertIn("--draft --verify-tag", self.source)
        self.assertNotIn("gh release edit", self.source)

    def test_release_prepares_auditable_outputs_without_device_access(self):
        for output in ("pico4-release-manifest.json", "pico4-sbom.cdx.json", "SHA256SUMS"):
            self.assertIn(output, self.source)
        self.assertNotRegex(self.source, r"(?m)^\s+run:.*\badb\b")


class PicoDeviceAcceptanceWorkflowContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = DEVICE_WORKFLOW.read_text(encoding="utf-8")

    def test_device_stage_is_manual_only_and_immutable_tag_only(self):
        self.assertRegex(self.source, r"(?m)^  workflow_dispatch:$")
        self.assertNotRegex(self.source, r"(?m)^  (pull_request|pull_request_target|push):$")
        self.assertIn('[[ "$GITHUB_REF_TYPE" == tag ]]', self.source)
        self.assertIn("pico4-release.py", self.source)

    def test_default_verification_job_cannot_invoke_adb(self):
        verify = self.source.split("  verify-candidate:", 1)[1].split("  device-acceptance:", 1)[0]
        self.assertNotRegex(verify, r"(?m)^\s+run:.*\badb\b")
        self.assertNotIn("--execute", verify)
        self.assertIn("runs-on: ubuntu-24.04", verify)

    def test_device_write_requires_boolean_confirmation_environment_and_lock(self):
        self.assertIn("if: inputs.execute_device_install", self.source)
        self.assertIn("environment: pico4-device-acceptance", self.source)
        self.assertIn("runs-on: [self-hosted, linux, x64, overte-pico4-device]", self.source)
        self.assertIn('INSTALL $GITHUB_REF_NAME', self.source)
        self.assertIn("pico-device-lock.sh run", self.source)
        self.assertIn("--execute", self.source)
        self.assertIn("--expected-signer-sha256", self.source)
        self.assertIn("PICO_RELEASE_CERT_SHA256", self.source)
        self.assertNotIn('"${{ inputs.confirmation }}"', self.source)

    def test_actions_are_pinned_and_checkout_is_credential_free(self):
        actions = ACTION_USE.findall(self.source)
        self.assertGreaterEqual(len(actions), 4)
        self.assertEqual([action for action in actions if not FULL_SHA_ACTION.fullmatch(action)], [])
        self.assertEqual(self.source.count("persist-credentials: false"), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
