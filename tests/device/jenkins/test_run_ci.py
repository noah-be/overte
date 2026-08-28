#!/usr/bin/env python3
"""Device-free tests for the local Jenkins glue."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
import subprocess
import xml.etree.ElementTree as ET


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SPEC = importlib.util.spec_from_file_location("overte_device_run_ci", HERE / "run_ci.py")
RUN_CI = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(RUN_CI)


class JenkinsGlueTest(unittest.TestCase):
    def configuration(self, temporary: Path) -> dict[str, str]:
        return {
            "OVERTE_CI_WORKSPACE": str(ROOT),
            "OVERTE_CI_ADAPTER_MANIFEST": "tests/device/adapters/mock/adapter.json",
            "OVERTE_CI_CATALOG": "tests/device/catalog.json",
            "OVERTE_CI_SUITE": "e2e-core",
            "OVERTE_CI_OUTPUT_DIR": str(temporary / "external-results"),
            "OVERTE_CI_FIXTURE_PUBLIC_HOST": "127.0.0.1",
            "OVERTE_CI_FIXTURE_BIND": "127.0.0.1",
            "OVERTE_CI_FIXTURE_PORT": "0",
            "OVERTE_CI_ALLOW_VIRTUAL": "1",
            "OVERTE_DEVICE_TARGET_SELECTOR": "mock-e2e-target",
            "OVERTE_MOCK_E2E_STATE": str(temporary / "mock-state.json"),
            "OVERTE_DEVICE_LAUNCH_SETTLE_SECONDS": "0",
            "OVERTE_E2E_POLL_SECONDS": "0.05",
            "OVERTE_DEVICE_LOCK_ROOT": str(temporary / "locks"),
        }

    def ios_target_config(self, path: Path) -> dict:
        value = {
            "schemaVersion": 1,
            "targets": [
                {
                    "selector": "private-ios-one", "platform": "ios",
                    "testBuild": {
                        "contract": "overte-ios-e2e-v1",
                        "fixtureOrigin": "http://fixture.invalid:18080",
                    },
                },
                {
                    "selector": "private-ios-two", "platform": "ios",
                    "testBuild": {
                        "contract": "overte-ios-e2e-v1",
                        "fixtureOrigin": "http://other.invalid:18080",
                    },
                },
            ],
        }
        path.parent.mkdir(parents=True, mode=0o700)
        path.write_text(json.dumps(value), encoding="utf-8")
        path.chmod(0o600)
        return value

    def test_mock_core_run_fixture_cleanup_and_staging(self):
        with tempfile.TemporaryDirectory(prefix="overte-jenkins-test-") as name:
            temporary = Path(name)
            values = self.configuration(temporary)
            with patch.dict(os.environ, values, clear=False):
                self.assertEqual(0, RUN_CI.run_suite())
                state = json.loads(Path(values["OVERTE_MOCK_E2E_STATE"]).read_text())
                self.assertFalse(state["running"], "the universal runner must clean up its target")
                summary = json.loads(
                    (Path(values["OVERTE_CI_OUTPUT_DIR"]) / "summary.json").read_text())
                self.assertEqual("passed", summary["status"])
                self.assertTrue(
                    (Path(values["OVERTE_CI_OUTPUT_DIR"]) / "fixture-ready.json").is_file())

                publish_workspace = temporary / "publish-workspace"
                (publish_workspace / "tests/device").mkdir(parents=True)
                (publish_workspace / "tests/device/run.py").touch()
                staged = publish_workspace / "artifacts/core"
                os.environ["OVERTE_CI_WORKSPACE"] = str(publish_workspace)
                os.environ["OVERTE_CI_STAGED_OUTPUT_DIR"] = str(staged)
                self.assertEqual(0, RUN_CI.stage_results())
                self.assertTrue((staged / "junit.xml").is_file())
                self.assertFalse((staged / "pipeline-error.txt").exists())

    def test_embedded_core_run_needs_no_network_fixture(self):
        with tempfile.TemporaryDirectory(prefix="overte-jenkins-embedded-test-") as name:
            temporary = Path(name)
            values = self.configuration(temporary)
            values["OVERTE_CI_FIXTURE_MODE"] = "embedded"
            values.pop("OVERTE_CI_FIXTURE_PUBLIC_HOST")
            with patch.dict(os.environ, values, clear=False):
                os.environ.pop("OVERTE_CI_FIXTURE_PUBLIC_HOST", None)
                self.assertEqual(0, RUN_CI.run_suite())
            output = Path(values["OVERTE_CI_OUTPUT_DIR"])
            self.assertEqual("passed", json.loads(
                (output / "summary.json").read_text())["status"])
            self.assertFalse((output / "fixture-ready.json").exists())

    def test_asset_and_sound_suites_receive_network_fixture_contracts(self):
        for suite in ("asset-smoke", "sound-smoke"):
            with self.subTest(suite=suite), tempfile.TemporaryDirectory(
                    prefix=f"overte-jenkins-{suite}-test-") as name:
                temporary = Path(name)
                values = self.configuration(temporary)
                values["OVERTE_CI_SUITE"] = suite
                values["OVERTE_CI_FIXTURE_MODE"] = "embedded"
                with patch.dict(os.environ, values, clear=False):
                    self.assertEqual(0, RUN_CI.run_suite())
                output = Path(values["OVERTE_CI_OUTPUT_DIR"])
                summary = json.loads((output / "summary.json").read_text())
                self.assertEqual("passed", summary["status"])
                self.assertTrue((output / "fixture-ready.json").is_file())

    def test_domain_suite_owns_fixture_and_passes_exact_ready_contract(self):
        with tempfile.TemporaryDirectory(prefix="overte-jenkins-domain-test-") as name:
            temporary = Path(name)
            domain_server = temporary / "domain-server"
            assignment_client = temporary / "assignment-client"
            for executable in (domain_server, assignment_client):
                executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
                executable.chmod(0o700)
            values = self.configuration(temporary)
            values.update({
                "OVERTE_CI_SUITE": "domain-smoke",
                "OVERTE_CI_DOMAIN_SERVER_EXECUTABLE": str(domain_server),
                "OVERTE_CI_ASSIGNMENT_CLIENT_EXECUTABLE": str(assignment_client),
            })
            ready = {
                "schemaVersion": 1,
                "domainUrl": "hifi://127.0.0.1:40102/0.0,2.0,4.0/0,0,0,1",
                "domainHost": "127.0.0.1",
                "domainId": "11111111-2222-4333-8444-555555555555",
                "requiredMarkers": [
                    "OVERTE_E2E_DOMAIN_EAST", "OVERTE_E2E_DOMAIN_FLOOR",
                    "OVERTE_E2E_DOMAIN_NORTH", "OVERTE_E2E_DOMAIN_ORIGIN",
                ],
            }
            domain_commands = []
            real_popen = subprocess.Popen

            class CompletedFixture:
                @staticmethod
                def poll():
                    return 0

            def spawn(command, *arguments, **options):
                if len(command) > 1 and str(command[1]).endswith("fixture/domain.py"):
                    domain_commands.append(command)
                    ready_path = Path(command[command.index("--ready-file") + 1])
                    ready_path.write_text(json.dumps(ready), encoding="utf-8")
                    fixture_output = Path(command[command.index("--output-dir") + 1])
                    fixture_output.mkdir()
                    (fixture_output / "domain-config.json").write_text(
                        "{}\n", encoding="utf-8")
                    (fixture_output / "domain-server.log").write_text(
                        "domain ready\n", encoding="utf-8")
                    (fixture_output / "assignment-client.log").write_text(
                        "assignments ready\n", encoding="utf-8")
                    return CompletedFixture()
                return real_popen(command, *arguments, **options)

            with patch.dict(os.environ, values, clear=False), \
                    patch.object(RUN_CI.subprocess, "Popen", side_effect=spawn):
                self.assertEqual(0, RUN_CI.run_suite())

            self.assertEqual(1, len(domain_commands))
            command = domain_commands[0]
            self.assertEqual("127.0.0.1", command[command.index("--bind") + 1])
            self.assertEqual(str(domain_server),
                             command[command.index("--domain-server") + 1])
            output = Path(values["OVERTE_CI_OUTPUT_DIR"])
            self.assertEqual("passed", json.loads(
                (output / "summary.json").read_text())[
                    "status"])
            self.assertTrue((output / "fixture-ready.json").is_file())
            self.assertTrue((output / "domain-fixture/domain-server.log").is_file())

    def test_domain_executables_must_be_absolute_executable_and_symlink_free(self):
        with tempfile.TemporaryDirectory(prefix="overte-domain-executable-test-") as name:
            executable = Path(name) / "domain-server"
            executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            values = {"OVERTE_CI_DOMAIN_SERVER_EXECUTABLE": str(executable)}
            with patch.dict(os.environ, values, clear=False):
                with self.assertRaisesRegex(ValueError, "executable file"):
                    RUN_CI.checked_executable("OVERTE_CI_DOMAIN_SERVER_EXECUTABLE")
                executable.chmod(0o700)
                self.assertEqual(executable.resolve(), RUN_CI.checked_executable(
                    "OVERTE_CI_DOMAIN_SERVER_EXECUTABLE"))
                link = Path(name) / "domain-link"
                link.symlink_to(executable)
                os.environ["OVERTE_CI_DOMAIN_SERVER_EXECUTABLE"] = str(link)
                with self.assertRaisesRegex(ValueError, "symbolic-link"):
                    RUN_CI.checked_executable("OVERTE_CI_DOMAIN_SERVER_EXECUTABLE")

    def test_controlled_android_suite_launches_before_capability_discovery(self):
        with tempfile.TemporaryDirectory(prefix="overte-android-bootstrap-test-") as name:
            manifest = Path(name) / "android.json"
            manifest.write_text(json.dumps({
                "schemaVersion": 1,
                "id": "android-phone-adb",
                "command": ["adapter.py", "--kind", "phone"],
            }), encoding="utf-8")
            before = json.dumps([{
                "selector": "private-target", "capabilities": ["app.launch"],
            }])
            ready = json.dumps([{
                "selector": "private-target",
                "capabilities": ["app.launch", "asset.load"],
            }])
            results = [
                subprocess.CompletedProcess([], 0, "{}\n", ""),
                subprocess.CompletedProcess([], 0, before, ""),
                subprocess.CompletedProcess([], 0, ready, ""),
            ]
            with patch.object(RUN_CI, "load_adapter_command", return_value=["adapter"]), \
                    patch.object(RUN_CI.subprocess, "run", side_effect=results) as execute, \
                    patch.object(RUN_CI.time, "sleep"):
                RUN_CI.prepare_controlled_android_target(
                    ROOT, manifest, "private-target", "asset-smoke", {"SAFE": "1"},
                )
            self.assertEqual("invoke", execute.call_args_list[0].args[0][1])
            self.assertEqual("app.launch", execute.call_args_list[0].args[0][5])
            self.assertEqual("discover", execute.call_args_list[1].args[0][1])
            self.assertEqual(3, execute.call_count)

    def test_private_selector_leak_is_quarantined(self):
        with tempfile.TemporaryDirectory(prefix="overte-jenkins-secret-test-") as name:
            temporary = Path(name)
            source = temporary / "outside/results"
            source.mkdir(parents=True)
            selector = "private-device-serial"
            (source / "adapter.log").write_text(f"target={selector}\n", encoding="utf-8")
            publish_workspace = temporary / "workspace"
            (publish_workspace / "tests/device").mkdir(parents=True)
            (publish_workspace / "tests/device/run.py").touch()
            staged = publish_workspace / "artifacts/smoke"
            values = {
                "OVERTE_CI_WORKSPACE": str(publish_workspace),
                "OVERTE_CI_OUTPUT_DIR": str(source),
                "OVERTE_CI_STAGED_OUTPUT_DIR": str(staged),
                "OVERTE_CI_SUITE": "smoke",
                "OVERTE_DEVICE_TARGET_SELECTOR": selector,
            }
            with patch.dict(os.environ, values, clear=False):
                self.assertEqual(2, RUN_CI.stage_results())
            self.assertFalse((staged / "adapter.log").exists())
            self.assertNotIn(selector, (staged / "pipeline-error.txt").read_text())
            junit = ET.parse(staged / "junit.xml").getroot()
            self.assertEqual("1", junit.attrib["errors"])

    def test_private_selector_in_result_file_or_directory_name_is_quarantined(self):
        for relative in (
                Path("diagnostic-private-device-serial.json"),
                Path("private-device-serial-diagnostics/report.json")):
            with self.subTest(relative=relative), tempfile.TemporaryDirectory(
                    prefix="overte-jenkins-secret-name-test-") as name:
                temporary = Path(name)
                source = temporary / "outside/results"
                (source / relative).parent.mkdir(parents=True)
                (source / relative).write_text("public content\n", encoding="utf-8")
                publish_workspace = temporary / "workspace"
                (publish_workspace / "tests/device").mkdir(parents=True)
                (publish_workspace / "tests/device/run.py").touch()
                staged = publish_workspace / "artifacts/smoke"
                values = {
                    "OVERTE_CI_WORKSPACE": str(publish_workspace),
                    "OVERTE_CI_OUTPUT_DIR": str(source),
                    "OVERTE_CI_STAGED_OUTPUT_DIR": str(staged),
                    "OVERTE_CI_SUITE": "smoke",
                    "OVERTE_DEVICE_TARGET_SELECTOR": "private-device-serial",
                }
                with patch.dict(os.environ, values, clear=False):
                    self.assertEqual(2, RUN_CI.stage_results())
                self.assertFalse((staged / relative).exists())
                self.assertNotIn(
                    "private-device-serial",
                    (staged / "pipeline-error.txt").read_text(encoding="utf-8"),
                )

    def test_result_root_and_staging_ancestor_symlinks_fail_closed(self):
        with tempfile.TemporaryDirectory(prefix="overte-jenkins-result-link-test-") as name:
            temporary = Path(name)
            real_external = temporary / "real-external"
            source = real_external / "results"
            source.mkdir(parents=True)
            (source / "junit.xml").write_text("<testsuite/>", encoding="utf-8")
            external_link = temporary / "external-link"
            external_link.symlink_to(real_external, target_is_directory=True)
            publish_workspace = temporary / "workspace"
            (publish_workspace / "tests/device").mkdir(parents=True)
            (publish_workspace / "tests/device/run.py").touch()
            staged = publish_workspace / "artifacts/smoke"
            values = {
                "OVERTE_CI_WORKSPACE": str(publish_workspace),
                "OVERTE_CI_OUTPUT_DIR": str(external_link / "results"),
                "OVERTE_CI_STAGED_OUTPUT_DIR": str(staged),
                "OVERTE_CI_SUITE": "smoke",
                "OVERTE_DEVICE_TARGET_SELECTOR": "private-device-serial",
            }
            with patch.dict(os.environ, values, clear=False):
                self.assertEqual(2, RUN_CI.stage_results())
            self.assertIn("symbolic link", (staged / "pipeline-error.txt").read_text())
            self.assertFalse((staged / "summary.json").exists())

            real_staging_parent = publish_workspace / "real-staging"
            real_staging_parent.mkdir()
            staging_link = publish_workspace / "staging-link"
            staging_link.symlink_to(real_staging_parent, target_is_directory=True)
            values["OVERTE_CI_OUTPUT_DIR"] = str(source)
            values["OVERTE_CI_STAGED_OUTPUT_DIR"] = str(staging_link / "smoke")
            with patch.dict(os.environ, values, clear=False):
                with self.assertRaisesRegex(ValueError, "symbolic-link components"):
                    RUN_CI.stage_results()
            self.assertFalse((real_staging_parent / "smoke").exists())

    def test_last_chance_cleanup_is_idempotent_and_device_free(self):
        with tempfile.TemporaryDirectory(prefix="overte-jenkins-cleanup-test-") as name:
            temporary = Path(name)
            state = temporary / "mock-state.json"
            state.write_text(json.dumps({"running": True, "foreground": True}), encoding="utf-8")
            values = {
                "OVERTE_CI_WORKSPACE": str(ROOT),
                "OVERTE_CI_ADAPTER_MANIFEST": "tests/device/adapters/mock/adapter.json",
                "OVERTE_DEVICE_TARGET_SELECTOR": "mock-e2e-target",
                "OVERTE_MOCK_E2E_STATE": str(state),
            }
            with patch.dict(os.environ, values, clear=False):
                self.assertEqual(0, RUN_CI.cleanup_target())
                self.assertEqual(0, RUN_CI.cleanup_target())
            self.assertFalse(json.loads(state.read_text())["running"])

    def test_runner_output_inside_checkout_is_rejected(self):
        with patch.dict(os.environ, {
            "OVERTE_CI_WORKSPACE": str(ROOT),
            "OVERTE_CI_OUTPUT_DIR": str(ROOT / "forbidden-device-results"),
        }, clear=False):
            with self.assertRaisesRegex(ValueError, "outside the source workspace"):
                RUN_CI.external_directory(ROOT, "OVERTE_CI_OUTPUT_DIR")

    def test_ios_preflight_delegates_to_privacy_safe_tunnel_status(self):
        with tempfile.TemporaryDirectory(prefix="overte-ios-preflight-"):
            values = {"OVERTE_CI_WORKSPACE": str(ROOT)}
            with patch.dict(os.environ, values, clear=False), \
                    patch.object(RUN_CI.subprocess, "run") as execute:
                execute.return_value.returncode = 0
                self.assertEqual(0, RUN_CI.ios_runtime_preflight())
            command = execute.call_args.args[0]
            self.assertIn("remotexpc_tunnel.py", command[1])
            self.assertIn("status", command)
            self.assertNotIn("udid", " ".join(command).lower())
            self.assertNotIn("appium-home", " ".join(command).lower())

    def test_ephemeral_fixture_origin_updates_only_selected_private_ios_target(self):
        with tempfile.TemporaryDirectory(prefix="overte-ios-origin-") as name:
            config = Path(name) / "private/job-targets.json"
            original = self.ios_target_config(config)
            values = {
                "OVERTE_IOS_JOB_TARGET_CONFIG": str(config),
                "OVERTE_APPIUM_TARGETS": str(config),
            }
            with patch.dict(os.environ, values, clear=False):
                RUN_CI.update_ios_fixture_origin(
                    ROOT, "private-ios-one", "http://LAB-HOST.example:43127",
                )
            updated = json.loads(config.read_text(encoding="utf-8"))
            self.assertEqual(0o600, config.stat().st_mode & 0o777)
            self.assertEqual(
                "http://lab-host.example:43127",
                updated["targets"][0]["testBuild"]["fixtureOrigin"],
            )
            self.assertEqual(original["targets"][1], updated["targets"][1])

    def test_ios_fixture_origin_rejects_wrong_selector_symlink_and_invalid_origin(self):
        with tempfile.TemporaryDirectory(prefix="overte-ios-origin-negative-") as name:
            temporary = Path(name)
            config = temporary / "private/job-targets.json"
            self.ios_target_config(config)
            original = config.read_bytes()
            values = {
                "OVERTE_IOS_JOB_TARGET_CONFIG": str(config),
                "OVERTE_APPIUM_TARGETS": str(config),
            }
            with patch.dict(os.environ, values, clear=False):
                with self.assertRaisesRegex(ValueError, "exactly one iOS target"):
                    RUN_CI.update_ios_fixture_origin(
                        ROOT, "unknown-private-selector", "http://lab.example:40001",
                    )
                with self.assertRaisesRegex(ValueError, "invalid base URL"):
                    RUN_CI.update_ios_fixture_origin(
                        ROOT, "private-ios-one", "http://lab.example:40001/path",
                    )
            self.assertEqual(original, config.read_bytes())

            link = temporary / "job-targets-link.json"
            link.symlink_to(config)
            link_values = {
                "OVERTE_IOS_JOB_TARGET_CONFIG": str(link),
                "OVERTE_APPIUM_TARGETS": str(link),
            }
            with patch.dict(os.environ, link_values, clear=False):
                with self.assertRaisesRegex(ValueError, "symlink-free"):
                    RUN_CI.update_ios_fixture_origin(
                        ROOT, "private-ios-one", "http://lab.example:40001",
                    )
            self.assertEqual(original, config.read_bytes())

    def test_ios_sync_uses_private_per_build_target_copy_and_exact_run(self):
        with tempfile.TemporaryDirectory(prefix="overte-ios-sync-glue-") as name:
            temporary = Path(name)
            source = temporary / "private/appium.json"
            source.parent.mkdir(mode=0o700)
            source.write_text(json.dumps({"schemaVersion": 1, "targets": []}), encoding="utf-8")
            source.chmod(0o600)
            job_config = temporary / "job/private-targets.json"
            values = {
                "OVERTE_CI_WORKSPACE": str(ROOT),
                "OVERTE_APPIUM_TARGETS": str(source),
                "OVERTE_IOS_JOB_TARGET_CONFIG": str(job_config),
                "OVERTE_IOS_ARTIFACT_ROOT": str(temporary / "job/artifacts"),
                "OVERTE_IOS_PRODUCER_RUN_ID": "12345",
                "OVERTE_DEVICE_TARGET_SELECTOR": "private-selector",
                "OVERTE_GITHUB_TOKEN": "private-token",
            }
            with patch.dict(os.environ, values, clear=False), \
                    patch.object(RUN_CI.subprocess, "run") as execute:
                execute.return_value.returncode = 0
                self.assertEqual(0, RUN_CI.ios_artifact_sync())
            self.assertTrue(job_config.is_file())
            self.assertEqual(0o600, job_config.stat().st_mode & 0o777)
            command = execute.call_args.args[0]
            self.assertIn("sync_fedora_artifacts.py", command[1])
            self.assertEqual("12345", command[command.index("--run-id") + 1])
            self.assertNotIn("private-token", command)
            self.assertNotIn("private-selector", command)
            self.assertNotIn("--target-selector", command)
            self.assertNotIn("--qt-host-cache-key", command)

    def test_failed_ios_sync_removes_private_target_copy(self):
        with tempfile.TemporaryDirectory(prefix="overte-ios-sync-failure-") as name:
            temporary = Path(name)
            source = temporary / "private/appium.json"
            source.parent.mkdir(mode=0o700)
            source.write_text("{}", encoding="utf-8")
            source.chmod(0o600)
            job_config = temporary / "job/private-targets.json"
            values = {
                "OVERTE_CI_WORKSPACE": str(ROOT),
                "OVERTE_APPIUM_TARGETS": str(source),
                "OVERTE_IOS_JOB_TARGET_CONFIG": str(job_config),
                "OVERTE_IOS_ARTIFACT_ROOT": str(temporary / "job/artifacts"),
                "OVERTE_IOS_PRODUCER_RUN_ID": "77",
                "OVERTE_DEVICE_TARGET_SELECTOR": "private-selector",
            }
            with patch.dict(os.environ, values, clear=False), \
                    patch.object(RUN_CI.subprocess, "run") as execute:
                execute.return_value.returncode = 2
                self.assertEqual(2, RUN_CI.ios_artifact_sync())
            self.assertFalse(job_config.exists())

    def test_ios_private_cleanup_removes_only_exact_build_paths(self):
        with tempfile.TemporaryDirectory(prefix="overte-ios-cleanup-") as name:
            temporary = Path(name)
            external = temporary / "private/build-17"
            artifact = external / "private-ios-artifacts"
            config = external / "private-ios-targets.json"
            artifact.mkdir(parents=True, mode=0o700)
            external.chmod(0o700)
            (artifact / "signed.ipa").write_bytes(b"private signed bytes")
            (artifact / "receipt.json").write_text("{}", encoding="utf-8")
            config.write_text("{}", encoding="utf-8")
            config.chmod(0o600)
            sibling = external / "smoke/junit.xml"
            sibling.parent.mkdir()
            sibling.write_text("<testsuite/>", encoding="utf-8")
            values = {
                "OVERTE_CI_WORKSPACE": str(ROOT),
                "OVERTE_EXTERNAL_RESULT_ROOT": str(external),
                "OVERTE_IOS_ARTIFACT_ROOT": str(artifact),
                "OVERTE_IOS_JOB_TARGET_CONFIG": str(config),
            }
            with patch.dict(os.environ, values, clear=False):
                self.assertEqual(0, RUN_CI.cleanup_ios_private())
                self.assertEqual(0, RUN_CI.cleanup_ios_private())
            self.assertFalse(artifact.exists())
            self.assertFalse(config.exists())
            self.assertTrue(sibling.is_file())

    def test_ios_private_cleanup_rejects_scope_escape_and_artifact_symlink(self):
        with tempfile.TemporaryDirectory(prefix="overte-ios-cleanup-negative-") as name:
            temporary = Path(name)
            external = temporary / "private/build-18"
            external.mkdir(parents=True, mode=0o700)
            outside = temporary / "must-survive"
            outside.mkdir()
            secret = outside / "signed.ipa"
            secret.write_bytes(b"must survive")
            config = external / "private-ios-targets.json"
            config.write_text("{}", encoding="utf-8")
            config.chmod(0o600)
            values = {
                "OVERTE_CI_WORKSPACE": str(ROOT),
                "OVERTE_EXTERNAL_RESULT_ROOT": str(external),
                "OVERTE_IOS_ARTIFACT_ROOT": str(outside),
                "OVERTE_IOS_JOB_TARGET_CONFIG": str(config),
            }
            with patch.dict(os.environ, values, clear=False):
                with self.assertRaisesRegex(ValueError, "exact build-result scope"):
                    RUN_CI.cleanup_ios_private()
            self.assertTrue(secret.is_file())
            self.assertTrue(config.is_file())

            artifact_link = external / "private-ios-artifacts"
            artifact_link.symlink_to(outside, target_is_directory=True)
            values["OVERTE_IOS_ARTIFACT_ROOT"] = str(artifact_link)
            with patch.dict(os.environ, values, clear=False):
                with self.assertRaisesRegex(ValueError, "symlink-free"):
                    RUN_CI.cleanup_ios_private()
            self.assertTrue(secret.is_file())
            self.assertTrue(artifact_link.is_symlink())

    @unittest.skipIf(os.name == "nt", "POSIX process-group behavior")
    def test_stop_process_terminates_the_complete_child_group(self):
        with tempfile.TemporaryDirectory(prefix="overte-process-group-") as name:
            child_pid = Path(name) / "child.pid"
            process = __import__("subprocess").Popen([
                __import__("sys").executable, "-c",
                "import pathlib,subprocess,sys,time; "
                "p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']); "
                f"pathlib.Path({str(child_pid)!r}).write_text(str(p.pid)); time.sleep(60)",
            ], start_new_session=True)
            deadline = time.monotonic() + 5
            while not child_pid.exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue(child_pid.exists())
            nested_pid = int(child_pid.read_text(encoding="utf-8"))
            RUN_CI.stop_process(process, grace_seconds=1)
            deadline = time.monotonic() + 2
            while Path(f"/proc/{nested_pid}").exists() and time.monotonic() < deadline:
                time.sleep(0.02)
            if Path(f"/proc/{nested_pid}/stat").is_file():
                state = Path(f"/proc/{nested_pid}/stat").read_text().split()[2]
                self.assertEqual("Z", state, "nested process must be dead, at most awaiting reap")

    def test_jenkinsfile_has_required_safety_layers(self):
        source = (HERE / "Jenkinsfile").read_text(encoding="utf-8")
        for expected in (
            "agent { label 'overte-device-interactive' }",
            "lock(resource:",
            "withCredentials([string(",
            "timeout(time:",
            "ciPython('cleanup-target'",
            "OVERTE_TARGET_NEEDS_CLEANUP",
            "post {",
            "junit(testResults:",
            "archiveArtifacts(",
            "ciPython('ios-runtime-preflight')",
            "ciPython('ios-artifact-sync')",
            "ciPython('cleanup-ios-private'",
            "OVERTE_IOS_JOB_TARGET_CONFIG",
            "IOS_GITHUB_TOKEN_CREDENTIAL_ID",
            "IOS_AGE_IDENTITY_CREDENTIAL_ID",
        ):
            self.assertIn(expected, source)
        self.assertLess(source.index("runDeviceSuite('smoke'"),
                        source.index("runDeviceSuite('stability'"))
        self.assertLess(source.index("runDeviceSuite('stability'"),
                        source.index("runDeviceSuite('lifecycle-stability'"))
        self.assertIn("!params.TARGET_PROFILE.startsWith('desktop-')", source)


if __name__ == "__main__":
    unittest.main()
