#!/usr/bin/env python3
"""Black-box regression tests for the project-suite CLI."""

from pathlib import Path
import json
import shutil
import subprocess
import sys
import tempfile
import unittest


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


if __name__ == "__main__":
    unittest.main()
