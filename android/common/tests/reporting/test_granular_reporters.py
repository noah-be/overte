import os
import shutil
from pathlib import Path
import stat
import subprocess
import tempfile
import time
import unittest
import xml.etree.ElementTree as ET


ANDROID_ROOT = Path(__file__).resolve().parents[3]


def executable(path: Path, content: str) -> None:
    path.write_text("#!/usr/bin/env bash\nset -euo pipefail\n" + content, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


class GranularReporterTest(unittest.TestCase):
    def test_common_qml_zero_exit_cannot_hide_error_failure_or_skip_junit(self):
        for counter in ('errors', 'failures', 'skipped', None):
            with self.subTest(counter=counter), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                runner = root / 'qmltestrunner'
                executable(runner, '''
previous=""
for argument in "$@"; do
  if [[ "$previous" == -o && "$argument" == /*,junitxml ]]; then
    printf '%s' "$FIXTURE_JUNIT" >"${argument%,junitxml}"
  fi
  previous="$argument"
done
''')
                original = ('<testsuite tests="1" ' + counter + '="1"><testcase result="pass"/></testsuite>'
                            if counter else '<testsuite tests="1"><testcase name="standard-qt6"/></testsuite>')
                result = subprocess.run([ANDROID_ROOT / 'common/tests/qml/run-qml-tests.sh'],
                    env=os.environ | {'OVERTE_QML_TEST_RUNNER': str(runner),
                                      'OVERTE_TEST_REPORT_DIR': str(root / 'reports'), 'FIXTURE_JUNIT': original},
                    text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                self.assertEqual(1 if counter else 0, result.returncode, result.stdout)
                self.assertEqual(original, (root / 'reports/qml/TEST-qml.xml').read_text())

    def test_fixed_phone_runtime_is_required_and_results_cannot_disappear(self):
        for mode in ('parent-only', 'pass', 'failure', 'skip', 'missing-report', 'zero-tests', 'false-success', 'partial'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                android = root / 'android'
                qml = android / 'common/tests/qml'
                reporting = android / 'common/tests/reporting'
                phone = android / 'phone/tests'
                qml.mkdir(parents=True)
                reporting.mkdir(parents=True)
                (phone / 'qml').mkdir(parents=True)
                for source, target in ((ANDROID_ROOT / 'common/tests/qml/run-qml-tests.sh', qml / 'run-qml-tests.sh'),
                                       (ANDROID_ROOT / 'common/tests/reporting/atomic-junit-report.sh', reporting / 'atomic-junit-report.sh')):
                    shutil.copy2(source, target)
                runner = root / 'qmltestrunner'
                executable(runner, '''
previous=""
for argument in "$@"; do
  if [[ "$previous" == -o && "$argument" == /*,junitxml ]]; then
    printf '<testsuite tests="1"><testcase result="pass"/></testsuite>' >"${argument%,junitxml}"
  fi
  previous="$argument"
done
''')
                if mode != 'parent-only':
                    (phone / 'qml/tst_phone_places_delegates.qml').write_text('// process-control fixture')
                if mode not in ('parent-only', 'partial'):
                    (phone / 'qml/tst_phone_login_domain.qml').write_text('// process-control fixture')
                    (phone / 'phone-places-delegate-test.py').write_text('''
import os, sys
from pathlib import Path
Path(os.environ['PHONE_RUNTIME_ENTERED']).write_text('entered')
mode = os.environ['PHONE_RUNTIME_MODE']
report = Path(sys.argv[sys.argv.index('--junit') + 1])
if mode != 'missing-report':
    xml = '<testsuite tests="1"><testcase result="pass"/></testsuite>'
    if mode == 'zero-tests': xml = '<testsuite tests="0"/>'
    if mode == 'false-success': xml = '<testsuite tests="1" errors="1"><testcase result="pass"/></testsuite>'
    report.write_text(xml)
raise SystemExit(7 if mode == 'failure' else 77 if mode == 'skip' else 0)
''')
                result = subprocess.run([qml / 'run-qml-tests.sh'], cwd=android,
                    env=os.environ | {'OVERTE_QML_TEST_RUNNER': str(runner),
                                      'OVERTE_TEST_REPORT_DIR': str(root / 'reports'),
                                      'PHONE_RUNTIME_MODE': mode, 'PHONE_RUNTIME_ENTERED': str(root / 'entered')},
                    text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                self.assertEqual(mode in ('parent-only', 'pass'), result.returncode == 0, result.stdout)
                self.assertEqual(mode not in ('parent-only', 'partial'), (root / 'entered').exists())
                if mode == 'skip':
                    self.assertEqual(1, result.returncode)
                if mode == 'failure':
                    self.assertEqual(7, result.returncode)
                if mode == 'false-success':
                    self.assertEqual('1', ET.parse(root / 'reports/qml/TEST-phone-places.xml').getroot().get('errors'))

    def test_qml_runners_discover_common_qt5_host_tool_paths(self):
        for relative in ("common/tests/qml/run-qml-tests.sh", "common/tests/qml/run-endurance-tests.sh"):
            source = (ANDROID_ROOT / relative).read_text(encoding="utf-8")
            self.assertIn("/usr/lib64/qt5/bin/qmltestrunner", source)
            self.assertIn("/usr/lib/qt5/bin/qmltestrunner", source)

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
            result = subprocess.run([ANDROID_ROOT / "common/tests/javascript/run-tests.sh"],
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
            result = subprocess.run([ANDROID_ROOT / "common/tests/javascript/run-tests.sh"],
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
            result = subprocess.run([ANDROID_ROOT / "common/tests/javascript/run-tests.sh"],
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
                    [ANDROID_ROOT / "common/tests/javascript/run-tests.sh"],
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
                [ANDROID_ROOT / "common/tests/javascript/run-tests.sh"], cwd=ANDROID_ROOT,
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
            result = subprocess.run([ANDROID_ROOT / "common/tests/javascript/run-tests.sh"],
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
            result = subprocess.run([ANDROID_ROOT / "common/tests/qml/run-qml-tests.sh"],
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
            result = subprocess.run([ANDROID_ROOT / "common/tests/qml/run-endurance-tests.sh"],
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
            result = subprocess.run([ANDROID_ROOT / "common/tests/native/run-native-tests.sh"],
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
source {str(ANDROID_ROOT / "common/tests/reporting/atomic-junit-report.sh")!r}
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
