import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET


ANDROID_ROOT = Path(__file__).resolve().parents[2]


def executable(path: Path, content: str) -> None:
    path.write_text("#!/usr/bin/env bash\nset -euo pipefail\n" + content, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


class GranularReporterTest(unittest.TestCase):
    def assert_failure_report(self, result, report: Path):
        self.assertEqual(7, result.returncode)
        self.assertIn("fixture-console-failure", result.stdout)
        root = ET.parse(report).getroot()
        self.assertEqual(1, len(root.findall(".//testcase")))
        self.assertIsNotNone(root.find(".//failure"))
        self.assertEqual([], list(report.parent.glob(".TEST-*.xml")))

    def test_javascript_preserves_failure_and_atomically_publishes_junit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            node = root / "node"
            executable(node, r'''
report=""
for argument in "$@"; do
  case "$argument" in --test-reporter-destination=/*) report="${argument#*=}" ;; esac
done
printf '<testsuite tests="1" failures="1"><testcase name="js"><failure/></testcase></testsuite>' >"$report"
echo fixture-console-failure
exit 7
''')
            result = subprocess.run([ANDROID_ROOT / "tests/javascript/run-tests.sh"],
                cwd=ANDROID_ROOT, env={**os.environ, "OVERTE_NODE_COMMAND": str(node),
                                      "OVERTE_TEST_REPORT_DIR": str(root / "reports")},
                text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            self.assert_failure_report(result, root / "reports/javascript/TEST-javascript.xml")

    def test_qml_preserves_failure_and_atomically_publishes_junit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runner = root / "qmltestrunner"
            executable(runner, r'''
report=""
previous=""
for argument in "$@"; do
  if [[ "$previous" == -o && "$argument" == /*,junitxml ]]; then report="${argument%,junitxml}"; fi
  previous="$argument"
done
printf '<testsuite tests="1" failures="1"><testcase name="qml"><failure/></testcase></testsuite>' >"$report"
echo fixture-console-failure
exit 7
''')
            result = subprocess.run([ANDROID_ROOT / "tests/qml/run-qml-tests.sh"],
                cwd=ANDROID_ROOT, env={**os.environ, "OVERTE_QML_TEST_RUNNER": str(runner),
                                      "OVERTE_TEST_REPORT_DIR": str(root / "reports")},
                text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            self.assert_failure_report(result, root / "reports/qml/TEST-qml.xml")

    def test_qml_endurance_preserves_failure_and_atomically_publishes_junit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runner = root / "qmltestrunner"
            executable(runner, r'''
report=""
previous=""
for argument in "$@"; do
  if [[ "$previous" == -o && "$argument" == /*,junitxml ]]; then report="${argument%,junitxml}"; fi
  previous="$argument"
done
printf '<testsuite tests="1" failures="1"><testcase name="qml-endurance"><failure/></testcase></testsuite>' >"$report"
echo fixture-console-failure
exit 7
''')
            result = subprocess.run([ANDROID_ROOT / "tests/qml/run-endurance-tests.sh"],
                cwd=ANDROID_ROOT, env={**os.environ, "OVERTE_QML_TEST_RUNNER": str(runner),
                                      "OVERTE_TEST_REPORT_DIR": str(root / "reports")},
                text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            self.assert_failure_report(
                result, root / "reports/qml-endurance/TEST-qml-endurance.xml")

    def test_native_preserves_failure_and_atomically_publishes_junit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cmake = root / "cmake"
            ctest = root / "ctest"
            executable(cmake, "exit 0\n")
            executable(ctest, r'''
report=""
previous=""
for argument in "$@"; do
  if [[ "$previous" == --output-junit ]]; then report="$argument"; fi
  previous="$argument"
done
printf '<testsuite tests="1" failures="1"><testcase name="native"><failure/></testcase></testsuite>' >"$report"
echo fixture-console-failure
exit 7
''')
            result = subprocess.run([ANDROID_ROOT / "tests/native/run-native-tests.sh"],
                cwd=ANDROID_ROOT, env={**os.environ, "OVERTE_CMAKE_COMMAND": str(cmake),
                                      "OVERTE_CTEST_COMMAND": str(ctest),
                                      "OVERTE_NATIVE_TEST_BUILD_DIR": str(root / "native-build"),
                                      "OVERTE_TEST_REPORT_DIR": str(root / "reports")},
                text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            self.assert_failure_report(result, root / "reports/native/TEST-native.xml")


if __name__ == "__main__":
    unittest.main()
