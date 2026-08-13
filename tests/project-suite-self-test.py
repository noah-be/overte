#!/usr/bin/env python3
"""Black-box and unit regression tests for the unified test runner."""

from pathlib import Path
import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tests/run-tests.py"
SPEC = importlib.util.spec_from_file_location("overte_run_tests", ROOT / "tests/run_tests.py")
RUN_TESTS = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = RUN_TESTS
SPEC.loader.exec_module(RUN_TESTS)


class UnifiedSuiteCliTests(unittest.TestCase):
    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        environment["OVERTE_SUITE_TEMP_ROOT"] = str(ROOT / "build/test-tmp/self-test")
        return subprocess.run(
            [sys.executable, str(RUNNER), *args], cwd=ROOT, env=environment, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def test_project_profiles_share_catalog_and_full_adds_native(self):
        quick = self.run_cli("--list", "--profile", "project-quick")
        full = self.run_cli("--list", "--profile", "project-full")
        self.assertEqual(quick.returncode, 0, quick.stderr)
        self.assertEqual(full.returncode, 0, full.stderr)
        self.assertIn("repository-health", quick.stdout)
        self.assertIn("pico:suite-runner", quick.stdout)
        self.assertNotIn("native-ctest", quick.stdout)
        self.assertIn("native-ctest", full.stdout)

    def test_imported_android_and_pico_profiles_are_selectable(self):
        android = self.run_cli("--list", "--profile", "android-fast")
        pico = self.run_cli("--list", "--profile", "pico-device-free")
        self.assertEqual(android.returncode, 0, android.stderr)
        self.assertEqual(pico.returncode, 0, pico.stderr)
        self.assertIn("android:suite-runner-self-test", android.stdout)
        self.assertNotIn("pico:suite-runner", android.stdout)
        self.assertEqual(len(pico.stdout.splitlines()), 30)
        self.assertTrue(all(line.startswith("pico:") for line in pico.stdout.splitlines()))

    def test_interface_and_category_filters_compose(self):
        result = self.run_cli(
            "--list", "--profile", "pico-device-free",
            "--interface", "android-pico", "--category", "audio")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("pico:audio-capture-state", result.stdout)
        self.assertIn("pico:audio-native-transport", result.stdout)
        self.assertNotIn("pico:openxr-loader", result.stdout)

    def test_unknown_selection_and_invalid_timeout_fail_closed(self):
        unknown = self.run_cli("--list", "--suite", "missing")
        timeout = self.run_cli("--timeout", "0")
        self.assertEqual(unknown.returncode, 2)
        self.assertIn("unknown suites", unknown.stderr)
        self.assertEqual(timeout.returncode, 2)


class UnifiedSuiteReportTests(unittest.TestCase):
    def test_xml_control_characters_are_replaced_and_output_is_bounded(self):
        self.assertEqual(RUN_TESTS.xml_safe("a\x00b"), "a\ufffdb")
        self.assertEqual(RUN_TESTS.xml_safe("a\ud800b\ufffec"), "a\ufffdb\ufffdc")
        output = RUN_TESTS.bounded_output("x" * (RUN_TESTS.MAX_REPORT_OUTPUT_BYTES + 1000))
        self.assertLessEqual(len(output.encode("utf-8")), RUN_TESTS.MAX_REPORT_OUTPUT_BYTES)
        self.assertIn("output truncated", output)

    def test_junit_write_is_parseable_and_replaces_existing_report(self):
        results = [{"id": "example", "kind": "contract", "status": "failed",
                    "message": "bad\x00value", "output": "details", "time": 0.25}]
        with tempfile.TemporaryDirectory(dir=ROOT / "build/test-tmp") as directory:
            report = Path(directory) / "result.xml"
            report.write_text("incomplete", encoding="utf-8")
            RUN_TESTS.write_junit(report, results, "self-test")
            parsed = ET.parse(report).getroot()
        self.assertEqual(parsed.attrib["failures"], "1")
        self.assertEqual(parsed.find("testcase/failure").attrib["message"], "bad\ufffdvalue")


if __name__ == "__main__":
    (ROOT / "build/test-tmp").mkdir(parents=True, exist_ok=True)
    unittest.main(verbosity=2)
