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
MACOS_RUNTIME_WORKFLOW = ROOT / ".github/workflows/macos-runtime.yml"
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
            '"android/common/tests/**"',
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

    def test_conan_cache_uses_the_deterministic_toolchain_key(self):
        restore = self.source.split("uses: actions/cache/restore@v5", 1)[1].split(
            "- name: Resolve dependencies", 1
        )[0]
        self.assertIn("key: ${{ steps.cache-key.outputs.conan }}", restore)
        self.assertIn("macos-conan-v2-${{ env.OVERTE_MACOS_ARCH }}-", restore)
        self.assertIn("macos-complete-x86_64-qt-aqt-", restore)
        self.assertIn("macos-partial-x86_64-qt-aqt-", restore)
        self.assertLess(
            restore.index("macos-conan-v2-${{ env.OVERTE_MACOS_ARCH }}-"),
            restore.index("macos-complete-x86_64-qt-aqt-"),
        )

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
        self.assertIn("steps.cache-key.outputs.conan", complete_save)
        self.assertIn("steps.resolve-dependencies.outcome == 'failure'", partial_save)
        self.assertIn("steps.cache-key.outputs.conan", partial_save)
        self.assertIn("${{ github.run_id }}", partial_save)
        self.assertIn("${{ github.run_attempt }}", partial_save)

    def test_dependency_failure_is_propagated_after_partial_cache_save(self):
        failure_gate = self.source.split("- name: Require resolved dependencies", 1)[1].split(
            "- name: Configure and build client", 1
        )[0]
        self.assertIn("steps.resolve-dependencies.outcome == 'failure'", failure_gate)
        self.assertIn("run: exit 1", failure_gate)

    def test_sccache_is_bounded_and_every_compiler_language_is_watched(self):
        self.assertIn("SCCACHE_DIR: ${{ github.workspace }}/.sccache", self.source)
        maximum = re.search(r"(?m)^\s+SCCACHE_CACHE_SIZE:\s*(\d+)M\s*$", self.source)
        self.assertIsNotNone(maximum)
        self.assertGreaterEqual(int(maximum.group(1)), 1024)
        self.assertLessEqual(int(maximum.group(1)), 2048)
        self.assertIn("brew list sccache", self.source)
        self.assertNotRegex(self.source, r"(?m)^\s+CCACHE_")
        for language in ("C", "CXX", "OBJC", "OBJCXX"):
            self.assertIn(
                f"CMAKE_{language}_COMPILER_LAUNCHER: "
                "${{ github.workspace }}/macos/ci/compiler-watchdog.py;--",
                self.source,
            )

    def test_monitoring_contracts_run_before_cache_restore_and_build(self):
        monitoring = self.source.index("- name: Verify macOS monitoring contracts")
        cache = self.source.index("- name: Cache Conan packages")
        build = self.source.index("- name: Configure and build client")
        self.assertLess(monitoring, cache)
        self.assertLess(monitoring, build)
        self.assertIn(
            "python3 macos/tests/source-contract-test.py",
            self.source[monitoring:cache],
        )

    def test_compiler_cache_restores_complete_before_partial_generations(self):
        compiler_cache = self.source.split(
            "- name: Restore bounded compiler recovery cache", 1
        )[1]
        restore = compiler_cache.split("- name: Configure compiler cache", 1)[0]
        complete = "steps.cache-key.outputs.sccache_complete_prefix"
        partial = "steps.cache-key.outputs.sccache_partial_prefix"
        self.assertIn("path: ${{ env.SCCACHE_DIR }}", restore)
        self.assertIn("key: ${{ steps.cache-key.outputs.sccache_complete }}", restore)
        self.assertIn(complete, restore)
        self.assertIn(partial, restore)
        self.assertLess(restore.index(complete), restore.index(partial))

    def test_cache_key_fingerprints_toolchain_platform_configuration_and_inputs(self):
        key_step = self.source.split(
            "- name: Select deterministic toolchain and cache keys", 1
        )[1].split("- name: Cache Conan packages", 1)[0]
        for required in (
            "xcrun --find clang",
            "compiler_digest",
            "compiler_version",
            "xcodebuild -version",
            "xcrun --sdk macosx --show-sdk-version",
            "xcrun --sdk macosx --show-sdk-build-version",
            "$OVERTE_MACOS_ARCH",
            "$OVERTE_MACOS_BUILD_TYPE",
            "$MACOSX_DEPLOYMENT_TARGET",
            "$OVERTE_MACOS_QT_SOURCE",
            "toolchain_inputs",
            "source_inputs",
            "git ls-files -s",
            "shasum -a 256",
        ):
            self.assertIn(required, key_step)
        self.assertIn("compiler_fingerprint", key_step)
        self.assertIn("macos-sccache-v3-", key_step)
        self.assertIn("macos-conan-v2-", key_step)

    def test_monitoring_only_changes_do_not_strand_compatible_sccache_entries(self):
        key_step = self.source.split(
            "- name: Select deterministic toolchain and cache keys", 1
        )[1].split("- name: Cache Conan packages", 1)[0]
        compiler_key = key_step.split('base="macos-sccache-v3-', 1)[1].split(
            '"', 1
        )[0]
        self.assertIn("${compiler_fingerprint}", compiler_key)
        compiler_fingerprint = key_step.split('compiler_fingerprint="', 1)[1].split(
            'toolchain_fingerprint="', 1
        )[0]
        self.assertNotIn("compiler-watchdog.py", compiler_fingerprint)
        self.assertNotIn("source_inputs", compiler_fingerprint)
        restore = self.source.split(
            "- name: Restore bounded compiler recovery cache", 1
        )[1].split("- name: Restore resumable build-tree checkpoint", 1)[0]
        self.assertIn("macos-sccache-v2-${{ env.OVERTE_MACOS_ARCH }}-", restore)

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
        self.assertIn("steps.sccache-restore.outputs.cache-hit != 'true'", complete_save)
        self.assertIn("steps.cache-key.outputs.sccache_complete", complete_save)
        self.assertIn("always()", partial_save)
        self.assertIn("!cancelled()", partial_save)
        self.assertIn("steps.build-client.outcome == 'failure'", partial_save)
        self.assertIn("steps.cache-key.outputs.sccache_partial_prefix", partial_save)
        self.assertIn("${{ github.run_id }}", partial_save)
        self.assertIn("${{ github.run_attempt }}", partial_save)
        self.assertIn("steps.build-client.outcome == 'failure'", failure_gate)
        self.assertIn("run: exit 1", failure_gate)

    def test_build_tree_restores_exact_complete_then_same_toolchain_partial(self):
        key_step = self.source.split(
            "- name: Select deterministic toolchain and cache keys", 1
        )[1].split("- name: Cache Conan packages", 1)[0]
        self.assertIn("build_base=\"macos-build-tree-v1-", key_step)
        self.assertIn("${toolchain_fingerprint}", key_step)
        self.assertIn("build_complete=${build_base}-complete-${source_inputs}", key_step)
        self.assertIn("build_complete_prefix=${build_base}-complete-", key_step)
        self.assertIn("build_partial_prefix=${build_base}-partial-", key_step)
        self.assertIn("macos/ci/build-tree-checkpoint.py", key_step)

        restore = self.source.split(
            "- name: Restore resumable build-tree checkpoint", 1
        )[1].split("- name: Configure compiler cache", 1)[0]
        self.assertIn("id: build-tree-restore", restore)
        self.assertIn("path: build", restore)
        self.assertIn("key: ${{ steps.cache-key.outputs.build_complete }}", restore)
        self.assertIn("steps.cache-key.outputs.build_complete_prefix", restore)
        self.assertIn("steps.cache-key.outputs.build_partial_prefix", restore)
        self.assertLess(
            restore.index("steps.cache-key.outputs.build_complete_prefix"),
            restore.index("steps.cache-key.outputs.build_partial_prefix"),
        )
        self.assertIn("- name: Normalize restored Ninja source timestamps", restore)
        self.assertIn("build-tree-checkpoint.py restore", restore)
        self.assertIn('--repository "$GITHUB_WORKSPACE" --build-dir build', restore)

    def test_build_tree_is_saved_after_orderly_success_or_failure(self):
        stop = self.source.index("- name: Stop compiler-cache server before snapshot")
        metadata_name = "- name: Record Ninja build-tree checkpoint metadata"
        metadata = self.source.split(metadata_name, 1)[1].split(
            "- name: Save complete compiler cache", 1
        )[0]
        complete_name = "- name: Save complete build-tree checkpoint"
        partial_name = "- name: Save partial build-tree checkpoint after build failure"
        complete = self.source.split(complete_name, 1)[1].split(partial_name, 1)[0]
        partial = self.source.split(partial_name, 1)[1].split(
            "- name: Require successful client build", 1
        )[0]
        self.assertLess(stop, self.source.index(complete_name))
        self.assertLess(stop, self.source.index(partial_name))
        self.assertLess(stop, self.source.index(metadata_name))
        self.assertLess(self.source.index(metadata_name), self.source.index(complete_name))
        self.assertLess(self.source.index(metadata_name), self.source.index(partial_name))
        self.assertIn("always()", metadata)
        self.assertIn("!cancelled()", metadata)
        self.assertIn("steps.build-client.outcome == 'success'", metadata)
        self.assertIn("steps.build-client.outcome == 'failure'", metadata)
        self.assertIn("build-tree-checkpoint.py record", metadata)
        self.assertIn("id: build-tree-metadata", metadata)
        for section in (complete, partial):
            self.assertIn("always()", section)
            self.assertIn("!cancelled()", section)
            self.assertIn("path: build", section)
            self.assertIn("steps.build-tree-metadata.outcome == 'success'", section)
        self.assertIn("steps.build-client.outcome == 'success'", complete)
        self.assertIn("steps.build-tree-restore.outputs.cache-hit != 'true'", complete)
        self.assertIn("steps.cache-key.outputs.build_complete", complete)
        self.assertIn("steps.build-client.outcome == 'failure'", partial)
        self.assertIn("steps.cache-key.outputs.build_partial_prefix", partial)
        self.assertIn("${{ github.run_id }}", partial)
        self.assertIn("${{ github.run_attempt }}", partial)

    def test_runner_telemetry_supervises_dependency_and_build_commands(self):
        self.assertIn(
            "MACOS_RUNNER_TELEMETRY_DIR: "
            "${{ github.workspace }}/.macos-runner-telemetry",
            self.source,
        )
        self.assertIn("PYTHONUNBUFFERED: '1'", self.source)
        dependencies = self.source.split("- name: Resolve dependencies", 1)[1].split(
            "- name: Save complete Conan cache", 1
        )[0]
        build = self.source.split("- name: Configure and build client", 1)[1].split(
            "- name: Report compiler-cache statistics", 1
        )[0]
        for section, command in (
            (dependencies, "-- macos/build-macos.sh deps"),
            (build, "-- macos/build-macos.sh build"),
        ):
            self.assertIn("python3 macos/ci/runner-telemetry.py", section)
            self.assertIn("--sample-interval 5", section)
            self.assertIn("--publish-interval 30", section)
            self.assertIn("--directory-interval 300", section)
            self.assertIn(command, section)
        self.assertIn('--watch build=build', build)
        self.assertIn('--watch conan="$CONAN_HOME"', build)
        self.assertIn('--watch sccache="$SCCACHE_DIR"', build)

    def test_runner_telemetry_and_build_diagnostics_are_always_uploaded(self):
        upload = self.source.split("- name: Upload smoke diagnostics", 1)[1].split(
            "- name: Upload application bundle", 1
        )[0]
        self.assertIn("if: always()", upload)
        self.assertIn(".macos-runner-telemetry", upload)
        self.assertIn("build/macos-build-diagnostics", upload)
        self.assertIn("if-no-files-found: ignore", upload)

    def test_sccache_server_is_stopped_before_every_snapshot(self):
        start = self.source.index("sccache --start-server")
        build = self.source.index("- name: Configure and build client")
        stop_step = self.source.split(
            "- name: Stop compiler-cache server before snapshot", 1
        )[1].split("- name: Save complete compiler cache", 1)[0]
        stop = self.source.index("sccache --stop-server")
        complete_save = self.source.index("- name: Save complete compiler cache")
        partial_save = self.source.index("- name: Save partial compiler cache")
        self.assertLess(start, build)
        self.assertLess(build, stop)
        self.assertLess(stop, complete_save)
        self.assertLess(stop, partial_save)
        self.assertIn("always()", stop_step)
        self.assertIn("!cancelled()", stop_step)

    def test_expensive_build_is_non_cancelling_and_has_step_timeout(self):
        self.assertIn("cancel-in-progress: false", self.source)
        build = self.source.split("- name: Configure and build client", 1)[1].split(
            "- name: Report compiler-cache statistics", 1
        )[0]
        timeout = re.search(r"timeout-minutes:\s*(\d+)", build)
        self.assertIsNotNone(timeout)
        self.assertGreaterEqual(int(timeout.group(1)), 60)
        self.assertLess(int(timeout.group(1)), 180)

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

    def test_runtime_reuses_a_built_app_without_rebuilding(self):
        source = MACOS_RUNTIME_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("artifact_run_id:", source)
        self.assertIn("if: github.event_name == 'workflow_dispatch'", source)
        self.assertIn("actions/download-artifact@018cc2cf5baa6db3ef3c5f8a56943fffe632ef53", source)
        self.assertIn("run-id: ${{ inputs.artifact_run_id }}", source)
        self.assertIn("mv build/runtime-artifact/Contents build/runtime-artifact/Overte.app/Contents", source)
        self.assertIn('chmod -R u+rx "$app/Contents/MacOS" "$app/Contents/Frameworks" "$app/Contents/PlugIns"', source)
        self.assertIn("OVERTE_MACOS_LLDB_TIMEOUT_SECONDS: '300'", source)
        self.assertIn("macos/ci/serverless-smoke.sh", source)
        self.assertIn("macos/ci/online-smoke.sh", source)
        self.assertNotIn("build-macos.sh build", source)
        self.assertIn("if: always()", source)

    def test_macos_bundles_share_one_glad_loader_state(self):
        linkage_check = (ROOT / "macos/ci/verify-glad-linkage.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("expected exactly one shared libglad dylib", linkage_check)
        self.assertIn("otool -L", linkage_check)
        self.assertIn("nm -gU", linkage_check)
        self.assertIn("_glad_glGetString", linkage_check)
        self.assertIn("_glad_debug_impl_glGetString", linkage_check)
        self.assertIn("macos/ci/verify-glad-linkage.sh", self.source)
        self.assertIn(
            "macos/ci/verify-glad-linkage.sh",
            MACOS_RUNTIME_WORKFLOW.read_text(encoding="utf-8"),
        )

    def test_build_progress_is_live_and_preserved(self):
        build_script = (ROOT / "macos/build-macos.sh").read_text(encoding="utf-8")
        self.assertIn("run-build-with-progress.py", build_script)
        self.assertIn("--log", build_script)
        self.assertIn("--result", build_script)
        self.assertIn("::notice title=macOS build progress::", build_script)
        self.assertIn("build/macos-build-diagnostics", self.source)


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
