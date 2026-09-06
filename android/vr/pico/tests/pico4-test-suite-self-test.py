#!/usr/bin/env python3
"""Black-box checks for the Pico 4 suite CLI."""

from pathlib import Path
import subprocess
import sys
import unittest
import importlib.util
import tempfile
import xml.etree.ElementTree as ET
from unittest.mock import patch
from contextlib import redirect_stdout, redirect_stderr
from io import StringIO


RUNNER = Path(__file__).with_name("pico4-test-suite.py")


class SuiteCliTests(unittest.TestCase):
    def run_cli(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([sys.executable, str(RUNNER), *arguments], text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)

    def test_catalog_names_are_unique_and_cover_core_categories(self):
        result = self.run_cli("--list")
        self.assertEqual(result.returncode, 0, result.stderr)
        rows = [line.split() for line in result.stdout.splitlines()]
        names = [row[0] for row in rows]
        categories = {row[1] for row in rows}
        self.assertEqual(len(names), len(set(names)))
        self.assertTrue({"android", "audio", "openxr", "webview", "interaction", "world"} <= categories)
        self.assertGreaterEqual(len(names), 20)

    def test_category_filter_is_exact(self):
        result = self.run_cli("--list", "--category", "openxr")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertGreaterEqual(len(result.stdout.splitlines()), 3)
        self.assertTrue(all(line.split()[1] == "openxr" for line in result.stdout.splitlines()))

    def test_unknown_selection_fails_with_usage_error(self):
        result = self.run_cli("--list", "--test", "does-not-exist")
        self.assertEqual(result.returncode, 2)
        self.assertIn("unknown tests", result.stderr)

    def test_nonpositive_timeout_is_rejected(self):
        result = self.run_cli("--timeout", "0")
        self.assertEqual(result.returncode, 2)
        self.assertIn("must be positive", result.stderr)


class SuiteOutcomeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("pico_suite_under_test", RUNNER)
        cls.runner = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = cls.runner
        spec.loader.exec_module(cls.runner)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def case(self, name, body="pass", requires=()):
        script = self.root / (name + ".py")
        script.write_text(body + "\n")
        return self.runner.Test(name, "fixture", (sys.executable, str(script)), requires)

    def execute(self, cases, *args):
        report = self.root / "report.xml"
        with patch.object(self.runner, "TESTS", tuple(cases)), patch.object(
                sys, "argv", [str(RUNNER), "--junit", str(report), *args]), \
                redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            code = self.runner.main()
        return code, ET.parse(report).getroot()

    def test_complete_selection_passes(self):
        code, report = self.execute([self.case("first"), self.case("second")])
        self.assertEqual(code, 0)
        self.assertEqual(report.get("tests"), "2")
        props = {p.get("name"): p.get("value") for p in report.findall("properties/property")}
        self.assertEqual(props["full_catalog_passed"], "true")

    def test_subset_is_explicit_not_full_catalog(self):
        code, report = self.execute([self.case("first"), self.case("second")], "--test", "first")
        self.assertEqual(code, 0)
        props = {p.get("name"): p.get("value") for p in report.findall("properties/property")}
        self.assertEqual(props["selection_complete"], "true")
        self.assertEqual(props["full_catalog_selected"], "false")
        self.assertEqual(props["full_catalog_passed"], "false")

    def test_missing_tool_cannot_pass_with_skip_missing(self):
        code, report = self.execute([self.case("missing", requires=("overte-nonexistent-suite-fixture-tool",))], "--skip-missing")
        self.assertEqual(code, 1)
        self.assertEqual(report.get("skipped"), "1")

    def test_fail_fast_keeps_every_selected_case(self):
        marker = self.root / "unexpected"
        code, report = self.execute([self.case("failure", "raise SystemExit(7)"),
            self.case("pending", "from pathlib import Path; Path(" + repr(str(marker)) + ").touch()")], "--fail-fast")
        self.assertEqual(code, 1)
        self.assertFalse(marker.exists())
        self.assertEqual(report.get("tests"), "2")
        self.assertEqual(report.get("failures"), "1")
        self.assertEqual(report.get("skipped"), "1")
        self.assertEqual(report.findall("testcase")[1].find("skipped").get("message"), "not run after fail-fast")

    def test_missing_tool_fail_fast_keeps_pending_case(self):
        code, report = self.execute([self.case("missing", requires=("overte-nonexistent-suite-fixture-tool",)),
                                    self.case("pending")], "--skip-missing", "--fail-fast")
        self.assertEqual(code, 1)
        self.assertEqual(report.get("tests"), "2")
        self.assertEqual(report.get("skipped"), "2")

    def test_launch_failure_is_reported_and_next_case_runs(self):
        absent = self.runner.Test("absent", "fixture", (str(self.root / "no-program"),))
        code, report = self.execute([absent, self.case("next")])
        self.assertEqual(code, 1)
        self.assertEqual(report.get("tests"), "2")
        self.assertEqual(report.get("failures"), "1")
        self.assertIsNone(report.findall("testcase")[1].find("failure"))
        self.assertNotIn(str(self.root), ET.tostring(report).decode())

    def test_timeout_is_failure_with_pending_case_retained(self):
        code, report = self.execute([self.case("timeout", "import time; time.sleep(10)"),
                                    self.case("pending")], "--timeout", "1", "--fail-fast")
        self.assertEqual(code, 1)
        self.assertEqual(report.get("failures"), "1")
        self.assertEqual(report.get("skipped"), "1")

    def test_empty_catalog_cannot_pass(self):
        code, report = self.execute([])
        self.assertEqual(code, 1)
        self.assertEqual(report.get("tests"), "0")


if __name__ == "__main__":
    unittest.main()
