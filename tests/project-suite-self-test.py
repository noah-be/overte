#!/usr/bin/env python3
"""Black-box regression tests for the project-suite CLI."""

from pathlib import Path
import contextlib
import importlib.util
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET


RUNNER = Path(__file__).with_name("run-project-tests.py")


class ProjectSuiteCliTests(unittest.TestCase):
    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([sys.executable, str(RUNNER), *args], text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def test_quick_profile_excludes_native_build(self):
        result = self.run_cli("--list")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("repository-health", result.stdout)
        self.assertIn("source-layout", result.stdout)
        self.assertIn("shared-script-behavior", result.stdout)
        self.assertIn("device-e2e-contracts", result.stdout)
        self.assertIn("documentation ", result.stdout)
        self.assertIn("repository-checks", result.stdout)
        self.assertIn("native-smoke", result.stdout)
        self.assertNotIn("native-ctest", result.stdout)

    def test_full_profile_includes_native_build(self):
        result = self.run_cli("--list", "--profile", "full")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("native-ctest", result.stdout)
        self.assertIn("documentation ", result.stdout)

    def test_coverage_cli_propagates_real_assertion_failures(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "tests").mkdir()
            (root / "src").mkdir()
            checker = root / "tests/project-coverage-test.py"
            shutil.copyfile(RUNNER.with_name("project-coverage-test.py"), checker)
            area = {"id": "fixture", "roots": ["src"], "automated": [], "native": [],
                    "hardware": ["audio-device-acceptance", "distributed-system-acceptance",
                                 "gpu-driver-acceptance"]}
            matrix = root / "tests/project-coverage.json"
            matrix.write_text(json.dumps({"schema": 1, "areas": [area]}))
            failed = subprocess.run([sys.executable, str(checker)], capture_output=True, text=True)
            self.assertNotEqual(failed.returncode, 0, failed.stderr)
            self.assertIn("FAILED (failures=1)", failed.stderr)
            area["automated"] = ["fixture-check"]
            matrix.write_text(json.dumps({"schema": 1, "areas": [area]}))
            passed = subprocess.run([sys.executable, str(checker)], capture_output=True, text=True)
            self.assertEqual(passed.returncode, 0, passed.stderr)

    def test_explicit_suite_can_select_native_independently(self):
        result = self.run_cli("--list", "--suite", "native-ctest")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.split()[0], "native-ctest")

    def test_device_control_plane_alias_selects_the_device_contract_suite(self):
        result = self.run_cli("--list", "--suite", "device-control-plane")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.split()[0], "device-e2e-contracts")

    def test_unknown_suite_and_invalid_timeout_fail(self):
        unknown = self.run_cli("--list", "--suite", "missing")
        self.assertEqual(unknown.returncode, 2)
        self.assertIn("unknown suites", unknown.stderr)
        timeout = self.run_cli("--timeout", "0")
        self.assertEqual(timeout.returncode, 2)

    def test_unittest_entrypoint_rejects_empty_and_failing_selections(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            command = [sys.executable, str(RUNNER.with_name("run-unittest-suite.py")), str(root)]
            empty = subprocess.run(command, capture_output=True, text=True, timeout=10)
            self.assertNotEqual(empty.returncode, 0)
            self.assertIn("no test cases", empty.stderr)
            fixture = root / "test_regression.py"
            fixture.write_text("import unittest\nclass Regression(unittest.TestCase):\n"
                               "    def test_behavior(self):\n        self.fail('regression-canary')\n")
            failed = subprocess.run(command, capture_output=True, text=True, timeout=10)
            self.assertNotEqual(failed.returncode, 0)
            self.assertIn("regression-canary", failed.stderr)
            fixture.write_text("import unittest\nclass Regression(unittest.TestCase):\n"
                               "    def test_behavior(self):\n        self.assertEqual(1 + 1, 2)\n")
            passed = subprocess.run(command, capture_output=True, text=True, timeout=10)
            self.assertEqual(passed.returncode, 0, passed.stderr)
            self.assertIn("Ran 1 test", passed.stderr)

    def test_unittest_entrypoint_keeps_repository_root_imports(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            helpers = root / "shared_helpers"
            helpers.mkdir()
            (helpers / "value.py").write_text("VALUE = 42\n")
            suite = root / "host-tests"
            suite.mkdir()
            (suite / "test_import.py").write_text(
                "import unittest\nfrom shared_helpers.value import VALUE\n"
                "class Regression(unittest.TestCase):\n"
                "    def test_import(self):\n        self.assertEqual(VALUE, 42)\n")
            result = subprocess.run([
                sys.executable, str(RUNNER.with_name("run-unittest-suite.py")), str(suite),
            ], cwd=root, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Ran 1 test", result.stderr)

    def test_new_host_regressions_fail_the_actual_registered_project_suite(self):
        # Execute the real registration/runner in a tiny workspace. Each selected
        # test deliberately fails, proving the command and JUnit cannot stay green.
        cases = {
            "device-result-schema": "tests/device/schema/test_regression.py",
            "device-jenkins": "tests/device/jenkins/test_regression.py",
            "desktop-input-protocol": "tests/device/adapters/desktop_oculix/test_wayland_libei_client.py",
            "performance-contracts": "tests/performance/schema/test_regression.py",
            "server-console-behavior": "server-console/test/open-url.test.js",
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "tests").mkdir()
            for filename in (RUNNER.name, "run-unittest-suite.py"):
                shutil.copyfile(RUNNER.with_name(filename), root / "tests" / filename)
            (root / "tests/platform-profile.json").write_text(json.dumps({
                "schema": 1, "platform": "shared", "suites": [],
            }))
            for filename in ("open-url.test.js", "file-tail.test.js", "notification-compat.test.js"):
                path = root / "server-console/test" / filename
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("require('node:test')('fixture', () => {});\n")
            for name, relative in cases.items():
                with self.subTest(suite=name):
                    fixture = root / relative
                    fixture.parent.mkdir(parents=True, exist_ok=True)
                    if fixture.suffix == ".py":
                        fixture.write_text("import unittest\nclass Regression(unittest.TestCase):\n"
                                           "    def test_behavior(self):\n        self.fail('regression-canary')\n")
                    else:
                        fixture.write_text("require('node:test')('fixture', () => {\n"
                                           "    throw new Error('regression-canary');\n});\n")
                    report = root / "result.xml"
                    result = subprocess.run([
                        sys.executable, str(root / "tests" / RUNNER.name), "--suite", name,
                        "--timeout", "10", "--junit", str(report),
                    ], capture_output=True, text=True, timeout=15)
                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                    self.assertIn("regression-canary", result.stderr)
                    xml = ET.parse(report).getroot()
                    self.assertEqual(xml.get("tests"), "1")
                    self.assertEqual(xml.get("failures"), "1")
                    self.assertEqual(xml.find("testcase").get("name"), name)

    def test_full_host_gate_reports_artifact_assertions_and_empty_discovery_as_failures(self):
        spec = importlib.util.spec_from_file_location(
            "control_plane", RUNNER.parent / "device/run_control_plane_tests.py")
        control_plane = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(control_plane)
        # Use the real registered command and full runner, restricting unrelated
        # expensive checks so the regression needs neither Qt nor SPDX packages.
        selected = [item for item in control_plane.commands("full") if item[0] == "artifact-identity"]
        self.assertEqual(len(selected), 1)
        self.assertFalse(selected[0][2], "Artifact validation is mandatory, not an optional QML check")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            test_directory = root / "tests/device/schema/artifact-identity"
            test_directory.mkdir(parents=True)
            shutil.copyfile(RUNNER.with_name("run-unittest-suite.py"), root / "tests/run-unittest-suite.py")
            fixture = test_directory / "test_regression.py"
            fixture.write_text("import unittest\nclass Regression(unittest.TestCase):\n"
                               "    def test_behavior(self):\n        self.fail('artifact-canary')\n")
            for failure in ("artifact-canary", "no test cases"):
                with self.subTest(failure=failure):
                    if failure == "no test cases":
                        fixture.unlink()
                    report = root / "result.xml"
                    with patch.object(control_plane, "REPOSITORY", root), \
                            patch.object(control_plane, "commands", return_value=selected), \
                            patch.object(sys, "argv", ["control-plane", "--profile", "full",
                                                      "--junit", str(report)]), \
                            contextlib.redirect_stdout(io.StringIO()):
                        result = control_plane.main()
                    self.assertEqual(result, 1)
                    xml = ET.parse(report).getroot()
                    self.assertEqual(xml.get("failures"), "1")
                    self.assertEqual(xml.get("skipped"), "0")
                    self.assertIn(failure, xml.find("testcase/failure").text)


if __name__ == "__main__":
    unittest.main()
