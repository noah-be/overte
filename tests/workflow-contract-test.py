#!/usr/bin/env python3
"""Security and reproducibility contracts for the Pico 4 CI workflow."""

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/project-tests.yml"
BUILD_WORKFLOW = ROOT / ".github/workflows/pico4-build.yml"
RELEASE_WORKFLOW = ROOT / ".github/workflows/pico4-release-candidate.yml"
DEVICE_WORKFLOW = ROOT / ".github/workflows/pico4-device-acceptance.yml"
GENERAL_BUILD_WORKFLOW = ROOT / ".github/workflows/build.yml"
ANDROID_TESTS_WORKFLOW = ROOT / ".github/workflows/android-tests.yml"
DOCUMENTATION_WORKFLOW = ROOT / ".github/workflows/documentation-checks.yml"
IOS_WORKFLOW = ROOT / ".github/workflows/ios-bootstrap.yml"
MACOS_WORKFLOW = ROOT / ".github/workflows/macos-bootstrap.yml"
ACTION_USE = re.compile(r"^\s*uses:\s*([^\s#]+)", re.MULTILINE)
FULL_SHA_ACTION = re.compile(r"^[^@\s]+@[0-9a-f]{40}$")


class GeneralBuildWorkflowContracts(unittest.TestCase):
    def test_documentation_and_contract_only_prs_skip_full_build_matrix(self):
        source = GENERAL_BUILD_WORKFLOW.read_text(encoding="utf-8")
        for path in (
            '"**/*.md"',
            '"docs/**"',
            '".github/workflows/build.yml"',
            '".github/workflows/documentation-checks.yml"',
            '".github/workflows/macos-bootstrap.yml"',
            '"android/tests/**"',
            '"ios/tests/**"',
            '"tests/workflow-contract-test.py"',
            '"tests/check-documentation.py"',
        ):
            self.assertIn(path, source)

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


class MacOSWorkflowContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MACOS_WORKFLOW.read_text(encoding="utf-8")

    def test_complete_conan_caches_are_restored_before_partial_caches(self):
        complete = "macos-complete-x86_64-qt-aqt-"
        partial = "macos-partial-x86_64-qt-aqt-"
        legacy = "macos-x86_64-qt-aqt-"
        restore = self.source.split("uses: actions/cache/restore@v5", 1)[1].split(
            "- name: Resolve dependencies", 1
        )[0]
        self.assertIn(f"key: {complete}", restore)
        self.assertIn(complete, restore)
        self.assertIn(partial, restore)
        self.assertIn(legacy, restore)
        self.assertLess(restore.index(complete), restore.index(partial))
        self.assertLess(restore.index(partial), restore.index(legacy))

    def test_cancelled_runs_never_save_conan_caches(self):
        complete_save = self.source.split("- name: Save complete Conan cache", 1)[1].split(
            "- name: Save partial Conan cache", 1
        )[0]
        partial_save = self.source.split(
            "- name: Save partial Conan cache after dependency failure", 1
        )[1].split("- name: Require resolved dependencies", 1)[0]
        self.assertIn("!cancelled()", complete_save)
        self.assertIn("!cancelled()", partial_save)

    def test_cache_kind_matches_dependency_outcome(self):
        self.assertIn("id: resolve-dependencies", self.source)
        self.assertIn("continue-on-error: true", self.source)
        complete_save = self.source.split("- name: Save complete Conan cache", 1)[1].split(
            "- name: Save partial Conan cache", 1
        )[0]
        partial_save = self.source.split(
            "- name: Save partial Conan cache after dependency failure", 1
        )[1].split("- name: Require resolved dependencies", 1)[0]
        self.assertIn("steps.resolve-dependencies.outcome == 'success'", complete_save)
        self.assertIn("macos-complete-x86_64-qt-aqt-", complete_save)
        self.assertIn("steps.resolve-dependencies.outcome == 'failure'", partial_save)
        self.assertIn("macos-partial-x86_64-qt-aqt-", partial_save)
        self.assertIn("${{ github.run_id }}", partial_save)

    def test_dependency_failure_is_propagated_after_partial_cache_save(self):
        failure_gate = self.source.split("- name: Require resolved dependencies", 1)[1].split(
            "- name: Configure and build client", 1
        )[0]
        self.assertIn("steps.resolve-dependencies.outcome == 'failure'", failure_gate)
        self.assertIn("run: exit 1", failure_gate)

    def test_compiler_cache_is_separate_bounded_and_used_by_both_languages(self):
        self.assertIn("CCACHE_DIR: ${{ github.workspace }}/.ccache", self.source)
        maximum = re.search(r"(?m)^\s+CCACHE_MAXSIZE:\s*(\d+)M\s*$", self.source)
        self.assertIsNotNone(maximum)
        self.assertGreaterEqual(int(maximum.group(1)), 1024)
        self.assertLessEqual(int(maximum.group(1)), 2048)
        self.assertIn("CMAKE_C_COMPILER_LAUNCHER: ccache", self.source)
        self.assertIn("CMAKE_CXX_COMPILER_LAUNCHER: ccache", self.source)
        compiler_cache = self.source.split("- name: Restore bounded compiler cache", 1)[1]
        complete = "macos-ccache-complete-v1-x86_64-"
        partial = "macos-ccache-partial-v1-x86_64-"
        restore = compiler_cache.split("- name: Configure compiler cache", 1)[0]
        self.assertIn(complete, restore)
        self.assertIn(partial, restore)
        self.assertLess(restore.index(complete), restore.index(partial))
        self.assertNotIn("macos-complete-x86_64", compiler_cache)
        self.assertIn('ccache --set-config "max_size=$CCACHE_MAXSIZE"', compiler_cache)

    def test_compiler_cache_checkpoints_preserve_success_and_failure_progress(self):
        build = self.source.split("- name: Configure and build client", 1)[1].split(
            "- name: Save complete compiler cache", 1
        )[0]
        complete_save = self.source.split("- name: Save complete compiler cache", 1)[1].split(
            "- name: Save partial compiler cache after build failure", 1
        )[0]
        partial_save = self.source.split(
            "- name: Save partial compiler cache after build failure", 1
        )[1].split("- name: Require successful client build", 1)[0]
        failure_gate = self.source.split("- name: Require successful client build", 1)[1].split(
            "- name: Verify application bundle", 1
        )[0]
        self.assertIn("id: build-client", build)
        self.assertIn("continue-on-error: true", build)
        self.assertIn("always()", complete_save)
        self.assertIn("!cancelled()", complete_save)
        self.assertIn("steps.build-client.outcome == 'success'", complete_save)
        self.assertIn("steps.ccache-restore.outputs.cache-hit != 'true'", complete_save)
        self.assertIn("macos-ccache-complete-v1-x86_64-", complete_save)
        self.assertIn("always()", partial_save)
        self.assertIn("!cancelled()", partial_save)
        self.assertIn("steps.build-client.outcome == 'failure'", partial_save)
        self.assertIn("macos-ccache-partial-v1-x86_64-", partial_save)
        self.assertIn("${{ github.run_id }}", partial_save)
        self.assertIn("steps.build-client.outcome == 'failure'", failure_gate)
        self.assertIn("run: exit 1", failure_gate)

    def test_startup_preflight_runs_before_entity_smokes_and_uploads_diagnostics(self):
        preflight = self.source.index("- name: Run application startup preflight")
        serverless = self.source.index("- name: Run serverless entity smoke")
        online = self.source.index("- name: Run online entity smoke")
        self.assertLess(preflight, serverless)
        self.assertLess(serverless, online)
        self.assertIn("macos/ci/startup-preflight.sh", self.source)
        self.assertIn("build/macos-startup-preflight", self.source)

    def test_built_application_is_preserved_when_runtime_smoke_fails(self):
        upload = self.source.split("- name: Upload application bundle", 1)[1]
        upload = upload.split("uses: actions/upload-artifact@", 1)[0]
        self.assertIn("always()", upload)
        self.assertIn("steps.build-client.outcome == 'success'", upload)


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
        self.assertIn("./build-pico.sh doctor", self.source)
        self.assertIn("./build-pico.sh deps --download", self.source)
        self.assertIn("./build-pico.sh build --stacktrace", self.source)
        self.assertIn("android/ci/verify-pico-apk.py", self.source)
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
        for contract in ("tests/run-project-tests.py", "./build-pico.sh deps --download",
                         "android/ci/verify-pico-apk.py", "--expected-version-code",
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
        self.assertIn("runs-on: ubuntu-latest", verify)

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
