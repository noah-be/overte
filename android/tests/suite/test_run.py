import tempfile
from pathlib import Path
import unittest
from unittest import mock
import xml.etree.ElementTree as ET

import run


class SuiteRunnerTest(unittest.TestCase):
    def test_catalog_has_unique_suites_and_known_tier(self):
        fast = run.load_suites(run.DEFAULT_CATALOG, "fast")
        self.assertGreater(len(fast), 0)
        self.assertEqual(len(fast), len({suite["id"] for suite in fast}))

    def test_catalog_rejects_unknown_tier(self):
        import json
        with tempfile.TemporaryDirectory() as directory:
            catalog = Path(directory) / "catalog.json"
            catalog.write_text(json.dumps({"schemaVersion": 1, "suites": [{
                "id": "bad", "kind": "jvm", "description": "bad tier",
                "command": ["true"], "tiers": ["typo"]
            }]}))
            with self.assertRaisesRegex(ValueError, "invalid tiers"):
                run.load_suites(catalog, "fast")

    def test_junit_report_records_failure_skip_and_output_safely(self):
        results = [
            {"id": "pass", "kind": "jvm", "status": "passed", "reason": "",
             "returncode": 0, "duration": 0.1, "output": "ok <safe>"},
            {"id": "fail", "kind": "native", "status": "failed", "reason": "",
             "returncode": 3, "duration": 0.2, "output": "bad & bounded"},
            {"id": "skip", "kind": "qml", "status": "skipped", "reason": "no tool",
             "returncode": 127, "duration": 0.0, "output": ""},
        ]
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "report.xml"
            run.write_report(results, report, "fast")
            root = ET.parse(report).getroot()
        self.assertEqual("3", root.attrib["tests"])
        self.assertEqual("1", root.attrib["failures"])
        self.assertEqual("1", root.attrib["skipped"])
        self.assertEqual("bad & bounded", root.find("testcase[@name='fail']/failure").text)

    def test_qml_suite_declares_missing_tool_as_optional(self):
        qml = next(suite for suite in run.load_suites(run.DEFAULT_CATALOG, "fast")
                   if suite["id"] == "qml-components")
        self.assertTrue(qml["optionalWhenToolMissing"])

    def test_invalid_catalog_always_produces_a_junit_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog = root / "broken.json"
            report_dir = root / "reports"
            catalog.write_text("{not-json", encoding="utf-8")
            argv = ["run.py", "fast", "--catalog", str(catalog),
                    "--report-dir", str(report_dir)]
            with mock.patch("sys.argv", argv):
                self.assertEqual(2, run.main())
            report = report_dir / "TEST-android-fast.xml"
            suite = ET.parse(report).getroot()
        self.assertEqual("1", suite.attrib["tests"])
        self.assertEqual("1", suite.attrib["failures"])
        self.assertIsNotNone(suite.find("testcase[@name='catalog-validation']/failure"))


if __name__ == "__main__":
    unittest.main()
