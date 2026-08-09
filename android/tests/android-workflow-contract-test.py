#!/usr/bin/env python3
"""Security and reproducibility contracts for Android Phone Actions workflows."""

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/android-tests.yml"
BUILD_WORKFLOW = ROOT / ".github/workflows/android-phone-build.yml"
RC_WORKFLOW = ROOT / ".github/workflows/android-phone-release-candidate.yml"
ACCEPTANCE_WORKFLOW = ROOT / ".github/workflows/android-phone-emulator-acceptance.yml"
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
        self.assertIn("android-tests-${{ github.workflow }}-${{ github.ref }}", self.source)
        self.assertIn("cancel-in-progress: ${{ github.event_name == 'pull_request' }}", self.source)
        timeouts = [int(value) for value in re.findall(r"timeout-minutes:\s*(\d+)", self.source)]
        self.assertGreaterEqual(len(timeouts), 4)
        self.assertLessEqual(max(timeouts), 45)

    def test_reports_are_small_and_short_lived(self):
        retentions = [int(value) for value in re.findall(r"retention-days:\s*(\d+)", self.source)]
        self.assertGreaterEqual(len(retentions), 5)
        self.assertLessEqual(max(retentions), 30)
        self.assertNotRegex(self.source, r"(?im)^\s+.*\.apk\s*$")

    def test_all_uploaded_artifacts_are_scoped_to_the_workflow_attempt(self):
        names = re.findall(
            r"(?m)^\s+uses: actions/upload-artifact@[^\n]+\n"
            r"\s+with:\n\s+name: ([^\n]+)$",
            self.source,
        )
        self.assertEqual(8, len(names))
        self.assertEqual(
            {
                "android-fast-results-${{ github.run_attempt }}",
                "android-fast-coverage-${{ github.run_attempt }}",
                "android-contract-results-${{ github.run_attempt }}",
                "android-host-coverage-${{ github.run_attempt }}",
                "android-mutation-extended-results-${{ github.run_attempt }}",
                "android-stability-results-${{ github.run_attempt }}",
                "android-endurance-results-${{ github.run_attempt }}",
                "android-regression-results-${{ github.run_attempt }}",
            },
            set(names),
        )

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

    def test_build_diagnostics_are_scoped_to_the_workflow_attempt(self):
        self.assertIn(
            "name: android-phone-build-reports-${{ github.run_id }}-"
            "${{ github.run_attempt }}",
            self.source,
        )
        self.assertNotIn(
            "name: android-phone-build-reports-${{ github.run_id }}\n",
            self.source,
        )


class AndroidPhoneReleaseCandidateWorkflowContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = RC_WORKFLOW.read_text(encoding="utf-8")

    def test_is_manual_read_only_and_protected(self):
        self.assertRegex(self.source, r"(?m)^  workflow_dispatch:$")
        self.assertNotRegex(self.source, r"(?m)^  (?:pull_request|pull_request_target|push):$")
        self.assertRegex(self.source, r"(?m)^permissions:\n  contents: read$")
        self.assertIn("environment: android-phone-release-candidate", self.source)
        self.assertIn("overte-android-phone-release", self.source)

    def test_source_version_and_unsigned_state_fail_closed(self):
        self.assertGreaterEqual(self.source.count("verify-phone-release.py"), 2)
        self.assertIn("ANDROID_PHONE_PUBLISHED_VERSION_CODE", self.source)
        self.assertIn("--expect-unsigned", self.source)
        self.assertIn("phoneInterface-release-unsigned.apk", self.source)
        self.assertIn("refs/tags/${{ inputs.release_tag }}", self.source)
        self.assertIn("persist-credentials: false", self.source)

    def test_release_values_are_not_interpolated_into_shell_programs(self):
        lines = self.source.splitlines()
        run_blocks = []
        for index, line in enumerate(lines):
            if line != "        run: |":
                continue
            body = []
            for candidate in lines[index + 1:]:
                if candidate and not candidate.startswith("          "):
                    break
                body.append(candidate)
            run_blocks.append("\n".join(body))
        self.assertGreaterEqual(len(run_blocks), 4)
        shell_programs = "".join(run_blocks)
        self.assertNotIn("${{ inputs.", shell_programs)
        self.assertNotIn("${{ vars.", shell_programs)
        for mapping in (
            "RELEASE_TAG: ${{ inputs.release_tag }}",
            "VERSION_CODE: ${{ inputs.version_code }}",
            "PUBLISHED_CODE_FLOOR: ${{ vars.ANDROID_PHONE_PUBLISHED_VERSION_CODE }}",
        ):
            self.assertGreaterEqual(self.source.count(mapping), 2)
        for argument in (
            '--tag "$RELEASE_TAG"',
            '--version-code "$VERSION_CODE"',
            '--published-code-floor "$PUBLISHED_CODE_FLOOR"',
        ):
            self.assertEqual(2, self.source.count(argument))

    def test_complete_gates_and_local_metadata_are_retained(self):
        for required in (
            "tests/run-tests.sh host", "./build-phone.sh deps --download",
            "./build-phone.sh prepare", "--expect-debuggable 0",
            "create-phone-release-metadata.py", "android/build/release/draft/",
        ):
            self.assertIn(required, self.source)
        self.assertNotIn("gh release create", self.source)
        self.assertNotIn("actions/attest-build-provenance", self.source)

    def test_candidate_artifact_is_scoped_to_the_workflow_attempt(self):
        self.assertIn(
            "name: android-phone-rc-${{ inputs.release_tag }}-"
            "${{ github.run_attempt }}",
            self.source,
        )
        self.assertNotIn(
            "name: android-phone-rc-${{ inputs.release_tag }}\n",
            self.source,
        )

    def test_candidate_build_respects_runner_cpu_budget(self):
        self.assertIn(
            "CMAKE_BUILD_PARALLEL_LEVEL=4 PICO_BUILD_JOBS=4 SHADERGEN_JOBS=4",
            self.source,
        )

    def test_mandatory_node_runtime_is_checked_before_host_tests(self):
        runtime_check = self.source.index("Verify mandatory host-test runtime")
        host_tests = self.source.index("Run complete device-free host tier")
        self.assertLess(runtime_check, host_tests)
        self.assertIn("android/ci/check-phone-host-runtime.sh", self.source)

    def test_candidate_diagnostics_are_scoped_to_the_workflow_attempt(self):
        self.assertIn(
            "name: android-phone-rc-reports-${{ github.run_id }}-"
            "${{ github.run_attempt }}",
            self.source,
        )
        self.assertNotIn(
            "name: android-phone-rc-reports-${{ github.run_id }}\n",
            self.source,
        )

    def test_actions_are_pinned_and_candidate_has_no_signing_secrets(self):
        actions = ACTION_USE.findall(self.source)
        self.assertEqual([action for action in actions if not FULL_SHA_ACTION.fullmatch(action)], [])
        self.assertNotIn("secrets.", self.source)
        self.assertNotIn("OVERTE_ANDROID_KEYSTORE", self.source)


class AndroidPhoneEmulatorAcceptanceWorkflowContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = ACCEPTANCE_WORKFLOW.read_text(encoding="utf-8")

    def test_requires_manual_install_approval_and_separate_environment(self):
        self.assertRegex(self.source, r"(?m)^  workflow_dispatch:$")
        self.assertNotRegex(self.source, r"(?m)^  (?:pull_request|pull_request_target|push):$")
        self.assertIn("if: inputs.approve_installation", self.source)
        self.assertIn("environment: android-phone-emulator-acceptance", self.source)
        self.assertIn("overte-android-phone-emulator", self.source)

    def test_verifies_digest_and_package_before_adb_installation(self):
        digest = self.source.index("sha256sum --check --strict")
        unsigned = self.source.index("--expect-unsigned")
        signing = self.source.index("apksigner sign")
        device = self.source.index("phone-device-test.sh")
        self.assertLess(digest, unsigned)
        self.assertLess(unsigned, signing)
        self.assertLess(signing, device)
        self.assertIn('PHONE_ALLOW_EMULATOR: "1"', self.source)

    def test_runtime_signature_is_ephemeral_and_never_published(self):
        self.assertEqual(2, self.source.count(
            "${{ runner.temp }}/android-phone-acceptance-${{ github.run_id }}-"
            "${{ github.run_attempt }}.apk"))
        self.assertIn("phoneInterface-release-unsigned.apk", self.source)
        self.assertNotIn('apk="android/build/emulator-candidate/phoneInterface-release.apk"', self.source)
        self.assertIn("openssl req -x509 -newkey rsa:2048 -nodes -days 1", self.source)
        self.assertIn("openssl pkcs8 -topk8 -nocrypt", self.source)
        self.assertIn('apksigner sign --key "$signing_dir/key.pk8"', self.source)
        self.assertIn("apksigner verify --verbose --print-certs", self.source)
        self.assertIn("trap 'rm -f -- \"$ACCEPTANCE_APK\"' EXIT", self.source)
        upload = self.source.split("uses: actions/upload-artifact@", 1)[1]
        self.assertNotIn("ACCEPTANCE_APK", upload)
        self.assertNotIn("android-phone-acceptance-", upload)

    def test_manual_inputs_are_not_interpolated_into_shell_programs(self):
        lines = self.source.splitlines()
        run_blocks = []
        for index, line in enumerate(lines):
            if line != "        run: |":
                continue
            body = []
            for candidate in lines[index + 1:]:
                if candidate and not candidate.startswith("          "):
                    break
                body.append(candidate)
            run_blocks.append("\n".join(body))
        self.assertGreaterEqual(len(run_blocks), 4)
        self.assertNotIn("${{ inputs.", "".join(run_blocks))
        for mapping in (
            "CANDIDATE_RUN_ID: ${{ inputs.candidate_run_id }}",
            "CANDIDATE_RUN_ATTEMPT: ${{ inputs.candidate_run_attempt }}",
            "APPROVED_APK_SHA256: ${{ inputs.apk_sha256 }}",
            "RELEASE_TAG: ${{ inputs.release_tag }}",
        ):
            self.assertIn(mapping, self.source)
        self.assertIn('gh run download "$CANDIDATE_RUN_ID"', self.source)
        self.assertIn(
            '[[ "$CANDIDATE_RUN_ATTEMPT" =~ ^[1-9][0-9]*$ ]]',
            self.source,
        )
        self.assertIn(
            '--name "android-phone-rc-$RELEASE_TAG-$CANDIDATE_RUN_ATTEMPT"',
            self.source,
        )
        self.assertNotIn('--name "android-phone-rc-$RELEASE_TAG"\n', self.source)
        self.assertIn(
            "printf '%s  %s\\n' \"$APPROVED_APK_SHA256\" \"$apk\"",
            self.source,
        )

    def test_candidate_attempt_is_a_required_manual_input(self):
        self.assertRegex(
            self.source,
            r"(?m)^      candidate_run_attempt:\n"
            r"        description: Successful release-candidate workflow run attempt\n"
            r"        required: true\n"
            r"        type: string$",
        )

    def test_device_report_is_run_attempt_scoped_and_outside_the_worktree(self):
        report_path = (
            "${{ runner.temp }}/android-phone-device-report-${{ github.run_id }}-"
            "${{ github.run_attempt }}"
        )
        self.assertEqual(2, self.source.count(report_path))
        self.assertIn(f"PHONE_TEST_REPORT: {report_path}", self.source)
        self.assertIn(f"path: {report_path}/", self.source)
        self.assertIn(
            "name: android-phone-emulator-acceptance-${{ github.run_id }}-"
            "${{ github.run_attempt }}",
            self.source,
        )
        self.assertNotIn(
            "name: android-phone-emulator-acceptance-${{ github.run_id }}\n",
            self.source,
        )
        self.assertNotIn("android/build/phone-device-report", self.source)
        self.assertNotIn("${{ github.workspace }}/android-phone-device-report", self.source)

    def test_actions_are_pinned_and_checkout_is_credential_free(self):
        actions = ACTION_USE.findall(self.source)
        self.assertEqual([action for action in actions if not FULL_SHA_ACTION.fullmatch(action)], [])
        self.assertIn("persist-credentials: false", self.source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
