import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[3]
RUNNER = ROOT / "common/tests/suite/run.py"


class EnduranceInfrastructureTest(unittest.TestCase):
    def test_cycle_counts_fail_closed(self):
        cases = [
            (ROOT / "common/tests/javascript/run-lifecycle-endurance.sh", "OVERTE_JS_ENDURANCE_CYCLES"),
            (ROOT / "common/tests/native/run-endurance-tests.sh", "OVERTE_NATIVE_ENDURANCE_CYCLES"),
        ]
        for script, variable in cases:
            for invalid in ("0", "-1", "not-a-number", "999999"):
                environment = dict(os.environ)
                environment[variable] = invalid
                result = subprocess.run(
                    [str(script)], cwd=ROOT, env=environment,
                    text=True, capture_output=True, check=False)
                self.assertEqual(2, result.returncode, (script, invalid, result.stderr))

    def test_endurance_junit_distinguishes_optional_skip_and_failure(self):
        catalog = {
            "schemaVersion": 1,
            "suites": [
                {
                    "id": "optional-tool", "kind": "qml", "tiers": ["endurance"],
                    "command": ["python3", "-c", "raise SystemExit(77)"],
                    "description": "missing optional host tool", "optionalWhenToolMissing": True,
                },
                {
                    "id": "real-failure", "kind": "native", "tiers": ["endurance"],
                    "command": ["python3", "-c", "raise SystemExit(1)"],
                    "description": "real endurance failure",
                },
            ],
        }
        with tempfile.TemporaryDirectory() as temporary:
            temporary_path = Path(temporary)
            catalog_path = temporary_path / "catalog.json"
            report_dir = temporary_path / "reports"
            catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
            result = subprocess.run([
                "python3", str(RUNNER), "endurance", "--catalog", str(catalog_path),
                "--report-dir", str(report_dir),
            ], cwd=ROOT, text=True, capture_output=True, check=False)
            report = ET.parse(report_dir / "TEST-android-endurance.xml").getroot()
        self.assertEqual(1, result.returncode)
        self.assertEqual("1", report.attrib["failures"])
        self.assertEqual("1", report.attrib["skipped"])
        self.assertIsNotNone(report.find("testcase[@name='optional-tool']/skipped"))
        self.assertIsNotNone(report.find("testcase[@name='real-failure']/failure"))


if __name__ == "__main__":
    unittest.main()
