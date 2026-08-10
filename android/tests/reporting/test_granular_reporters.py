import os
from pathlib import Path
import stat
import subprocess
import tempfile
import time
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
        with tempfile.TemporaryDirectory(prefix="report path with spaces ") as directory:
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

    def test_empty_javascript_report_invalidates_previous_result(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            node = root / "node"
            executable(node, "echo fixture-console-failure\nexit 7\n")
            report_dir = root / "reports/javascript"
            report_dir.mkdir(parents=True)
            report = report_dir / "TEST-javascript.xml"
            report.write_text(
                '<testsuite tests="1"><testcase name="previous"/></testsuite>',
                encoding="utf-8")
            result = subprocess.run([ANDROID_ROOT / "tests/javascript/run-tests.sh"],
                cwd=ANDROID_ROOT, env={**os.environ, "OVERTE_NODE_COMMAND": str(node),
                                      "OVERTE_TEST_REPORT_DIR": str(root / "reports")},
                text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            self.assertEqual(7, result.returncode)
            self.assertFalse(report.exists())
            self.assertIn("JUnit reporter produced no report", result.stdout)
            self.assertEqual([], list(report_dir.glob(".TEST-*.xml")))

    def test_successful_tool_without_junit_report_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            node = root / "node"
            executable(node, "echo fixture-console-success\n")
            report_dir = root / "reports/javascript"
            result = subprocess.run([ANDROID_ROOT / "tests/javascript/run-tests.sh"],
                cwd=ANDROID_ROOT, env={**os.environ, "OVERTE_NODE_COMMAND": str(node),
                                      "OVERTE_TEST_REPORT_DIR": str(root / "reports")},
                text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            self.assertEqual(1, result.returncode)
            self.assertIn("fixture-console-success", result.stdout)
            self.assertIn("JUnit reporter produced no report", result.stdout)
            self.assertFalse((report_dir / "TEST-javascript.xml").exists())
            self.assertEqual([], list(report_dir.glob(".TEST-*.xml")))

    def test_successful_tool_with_invalid_junit_fails_closed(self):
        for contents in ("not xml", '<testsuite tests="0"/>'):
            with self.subTest(contents=contents), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                node = root / "node"
                executable(node, r'''
report=""
for argument in "$@"; do
  case "$argument" in --test-reporter-destination=/*) report="${argument#*=}" ;; esac
done
printf '%s' "$FIXTURE_JUNIT" >"$report"
''')
                report_dir = root / "reports/javascript"
                report_dir.mkdir(parents=True)
                report = report_dir / "TEST-javascript.xml"
                report.write_text(
                    '<testsuite tests="1"><testcase name="stale"/></testsuite>',
                    encoding="utf-8")
                result = subprocess.run(
                    [ANDROID_ROOT / "tests/javascript/run-tests.sh"],
                    cwd=ANDROID_ROOT,
                    env={**os.environ, "OVERTE_NODE_COMMAND": str(node),
                         "OVERTE_TEST_REPORT_DIR": str(root / "reports"),
                         "FIXTURE_JUNIT": contents},
                    text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                self.assertEqual(1, result.returncode, result.stdout)
                self.assertIn("JUnit reporter produced an invalid report", result.stdout)
                self.assertFalse(report.exists())
                self.assertEqual([], list(report_dir.glob(".TEST-*.xml")))

    def test_successful_tool_publishes_positive_testsuites_aggregate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            node = root / "node"
            executable(node, r'''
report=""
for argument in "$@"; do
  case "$argument" in --test-reporter-destination=/*) report="${argument#*=}" ;; esac
done
printf '%s' "$FIXTURE_JUNIT" >"$report"
''')
            aggregate = ('<testsuites><testsuite tests="1">'
                         '<testcase name="current"/></testsuite></testsuites>')
            report = root / "reports/javascript/TEST-javascript.xml"
            result = subprocess.run(
                [ANDROID_ROOT / "tests/javascript/run-tests.sh"], cwd=ANDROID_ROOT,
                env={**os.environ, "OVERTE_NODE_COMMAND": str(node),
                     "OVERTE_TEST_REPORT_DIR": str(root / "reports"),
                     "FIXTURE_JUNIT": aggregate},
                text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            self.assertEqual(0, result.returncode, result.stdout)
            self.assertEqual("current", ET.parse(report).find(".//testcase").get("name"))

    def test_javascript_refuses_symlinked_report_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            node = root / "node"
            executable(node, r'''
touch "$TOOL_MARKER"
report=""
for argument in "$@"; do
  case "$argument" in --test-reporter-destination=/*) report="${argument#*=}" ;; esac
done
printf '<testsuite tests="0"/>' >"$report"
''')
            report_dir = root / "reports/javascript"
            report_dir.mkdir(parents=True)
            victim = root / "victim.xml"
            victim.write_text("private", encoding="utf-8")
            (report_dir / "TEST-javascript.xml").symlink_to(victim)
            result = subprocess.run([ANDROID_ROOT / "tests/javascript/run-tests.sh"],
                cwd=ANDROID_ROOT, env={**os.environ, "OVERTE_NODE_COMMAND": str(node),
                                      "OVERTE_TEST_REPORT_DIR": str(root / "reports"),
                                      "TOOL_MARKER": str(root / "tool-entered")},
                text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            self.assertEqual(1, result.returncode)
            self.assertIn("refusing to replace symlinked JUnit report", result.stdout)
            self.assertEqual("private", victim.read_text(encoding="utf-8"))
            self.assertFalse((root / "tool-entered").exists())
            self.assertEqual([], list(report_dir.glob(".TEST-*.xml")))

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

    def test_same_report_path_serializes_the_complete_runner_lifecycle(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runner = root / "runner"
            executable(runner, f'''
source {str(ANDROID_ROOT / "tests/reporting/atomic-junit-report.sh")!r}
overte_junit_prepare "$REPORT_DIR" TEST-shared.xml
trap overte_junit_cleanup EXIT
touch "$ROOT/entered-$ROLE"
if [[ "$ROLE" == first ]]; then
  while [[ ! -e "$ROOT/release-first" ]]; do sleep 0.02; done
fi
printf '<testsuite tests="1"><testcase name="%s"/></testsuite>' "$ROLE" >"$OVERTE_JUNIT_TEMP_REPORT"
overte_junit_publish
''')
            report_dir = root / "reports"
            report_dir.mkdir()
            report = report_dir / "TEST-shared.xml"
            report.write_text(
                '<testsuite tests="1"><testcase name="stale"/></testsuite>',
                encoding="utf-8")
            common = {**os.environ, "ROOT": str(root), "REPORT_DIR": str(report_dir)}
            first = subprocess.Popen([runner], env={**common, "ROLE": "first"})
            deadline = time.monotonic() + 3
            while not (root / "entered-first").exists() and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertTrue((root / "entered-first").exists())
            self.assertFalse(report.exists())

            timed_out = subprocess.run(
                [runner], env={**common, "ROLE": "timeout",
                               "OVERTE_JUNIT_LOCK_TIMEOUT_SECONDS": "0.05"},
                text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            self.assertEqual(1, timed_out.returncode)
            self.assertIn("timed out waiting for JUnit report lock", timed_out.stdout)
            self.assertFalse((root / "entered-timeout").exists())

            second = subprocess.Popen([runner], env={**common, "ROLE": "second"})
            time.sleep(0.2)
            self.assertFalse((root / "entered-second").exists())
            (root / "release-first").touch()
            self.assertEqual(0, first.wait(timeout=3))
            self.assertEqual(0, second.wait(timeout=3))

            self.assertEqual("second", ET.parse(report).find("testcase").attrib["name"])
            self.assertEqual([], list(report_dir.glob(".TEST-*.xml")))


if __name__ == "__main__":
    unittest.main()
