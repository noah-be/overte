import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest


ANDROID_ROOT = Path(__file__).resolve().parents[3]
RUNNER = ANDROID_ROOT / "common/tests/coverage/run-standalone-jvm-coverage.sh"


def executable(path: Path, content: str) -> None:
    path.write_text("#!/usr/bin/env bash\nset -euo pipefail\n" + content,
                    encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


class StandaloneJvmCoverageHarnessTest(unittest.TestCase):
    def fixture(self, root: Path, *, javac_fail: int = 0, java_fail: int = 0,
                verify_fail: int = 0) -> dict[str, str]:
        tools = root / "commands"
        tools.mkdir()
        jacoco_tools = root / "jacoco-tools"
        jacoco_tools.mkdir()
        (jacoco_tools / "jacocoagent.jar").write_text("agent", encoding="utf-8")
        (jacoco_tools / "jacococli.jar").write_text("cli", encoding="utf-8")

        javac = tools / "javac"
        java = tools / "java"
        verifier = tools / "verify"
        sha256sum = tools / "sha256sum"
        curl = tools / "curl"
        executable(javac, r'''
touch "$TOOL_STARTED"
count=0
[[ ! -f "$JAVAC_COUNT" ]] || read -r count <"$JAVAC_COUNT"
count=$((count + 1))
printf '%s\n' "$count" >"$JAVAC_COUNT"
[[ "${JAVAC_FAIL_CALL:-0}" != "$count" ]]
''')
        executable(java, r'''
touch "$TOOL_STARTED"
printf '%s\n' "$*" >>"$JAVA_LOG"
if [[ " $* " == *' -jar '* ]]; then
  xml=''
  html=''
  previous=''
  for argument in "$@"; do
    [[ "$previous" == --xml ]] && xml="$argument"
    [[ "$previous" == --html ]] && html="$argument"
    previous="$argument"
  done
  mkdir -p "$html"
  printf '<report/>\n' >"$xml"
  printf '<html>coverage</html>\n' >"$html/index.html"
  exit 0
fi
count=0
[[ ! -f "$JAVA_TEST_COUNT" ]] || read -r count <"$JAVA_TEST_COUNT"
count=$((count + 1))
printf '%s\n' "$count" >"$JAVA_TEST_COUNT"
printf 'execution-%s\n' "$count" >>"$EXECUTION_DATA"
[[ "${JAVA_FAIL_CALL:-0}" != "$count" ]]
''')
        executable(verifier, r'''
touch "$TOOL_STARTED"
printf '%s\n' "$1" >"$VERIFIED_PATH"
[[ "$1" == */.jvm-coverage.*/report.xml ]]
[[ ! -e "$FINAL_REPORT" ]]
[[ "${VERIFY_FAIL:-0}" == 0 ]]
''')
        executable(sha256sum, 'touch "$TOOL_STARTED"\nexit 0\n')
        executable(curl, 'touch "$TOOL_STARTED"\nexit 99\n')

        return {
            **os.environ,
            "OVERTE_JVM_COVERAGE_BUILD_DIR": str(root / "build"),
            "OVERTE_JVM_COVERAGE_REPORT_DIR": str(root / "reports"),
            "OVERTE_JVM_COVERAGE_TOOLS_DIR": str(jacoco_tools),
            "OVERTE_JAVAC_COMMAND": str(javac),
            "OVERTE_JAVA_COMMAND": str(java),
            "OVERTE_JVM_COVERAGE_VERIFY_COMMAND": str(verifier),
            "OVERTE_SHA256SUM_COMMAND": str(sha256sum),
            "OVERTE_CURL_COMMAND": str(curl),
            "TOOL_STARTED": str(root / "tool-started"),
            "JAVAC_COUNT": str(root / "javac-count"),
            "JAVAC_FAIL_CALL": str(javac_fail),
            "JAVA_LOG": str(root / "java-log"),
            "JAVA_TEST_COUNT": str(root / "java-test-count"),
            "JAVA_FAIL_CALL": str(java_fail),
            "EXECUTION_DATA": str(root / "build/jacoco.exec"),
            "VERIFIED_PATH": str(root / "verified-path"),
            "FINAL_REPORT": str(root / "reports/report.xml"),
            "VERIFY_FAIL": str(verify_fail),
        }

    def run_fixture(self, environment: dict[str, str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [RUNNER], cwd=ANDROID_ROOT, env=environment, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)

    def seed_stale_reports(self, root: Path) -> None:
        reports = root / "reports"
        (reports / "html").mkdir(parents=True)
        (reports / "report.xml").write_text("stale", encoding="utf-8")
        (reports / "html/index.html").write_text("stale", encoding="utf-8")

    def assert_no_published_or_staged_report(self, root: Path) -> None:
        reports = root / "reports"
        self.assertFalse((reports / "report.xml").exists())
        self.assertFalse((reports / "html").exists())
        self.assertEqual([], list(reports.glob(".jvm-coverage.*")))

    @unittest.skipUnless(os.name == "posix", "flock fixture is POSIX-specific")
    def test_staging_failure_invalidates_reports_without_starting_tools(self):
        import fcntl

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.seed_stale_reports(root)
            failing_mktemp = root / "failing-mktemp"
            executable(failing_mktemp, "exit 8\n")
            environment = self.fixture(root)
            environment["OVERTE_JVM_COVERAGE_MKTEMP_COMMAND"] = str(failing_mktemp)

            result = self.run_fixture(environment)

            self.assertEqual(8, result.returncode, result.stdout)
            self.assert_no_published_or_staged_report(root)
            self.assertFalse((root / "tool-started").exists())
            lock_path = Path(environment["OVERTE_JVM_COVERAGE_BUILD_DIR"] + ".lock")
            with lock_path.open("a", encoding="utf-8") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def test_early_failure_invalidates_old_report_and_cleans_staging(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.seed_stale_reports(root)
            result = self.run_fixture(self.fixture(root, javac_fail=1))
            self.assertEqual(1, result.returncode, result.stdout)
            self.assert_no_published_or_staged_report(root)
            self.assertFalse((root / "java-log").exists())

    def test_test_failure_stops_before_report_generation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = self.run_fixture(self.fixture(root, java_fail=3))
            self.assertEqual(1, result.returncode, result.stdout)
            self.assertEqual("3", (root / "java-test-count").read_text().strip())
            self.assertEqual(3, len((root / "java-log").read_text().splitlines()))
            self.assertFalse((root / "verified-path").exists())
            self.assert_no_published_or_staged_report(root)

    def test_verifier_failure_publishes_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = self.run_fixture(self.fixture(root, verify_fail=1))
            self.assertEqual(1, result.returncode, result.stdout)
            self.assertTrue((root / "verified-path").is_file())
            self.assert_no_published_or_staged_report(root)

    def test_success_verifies_staging_then_publishes_xml_last(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = self.run_fixture(self.fixture(root))
            self.assertEqual(0, result.returncode, result.stdout)
            reports = root / "reports"
            self.assertEqual("<report/>\n", (reports / "report.xml").read_text())
            self.assertTrue((reports / "html/index.html").is_file())
            self.assertEqual([], list(reports.glob(".jvm-coverage.*")))
            self.assertEqual("9", (root / "java-test-count").read_text().strip())
            calls = (root / "java-log").read_text().splitlines()
            self.assertEqual(10, len(calls))
            self.assertEqual(9, sum("append=true" in call for call in calls))
            verified = (root / "verified-path").read_text().strip()
            self.assertIn("/.jvm-coverage.", verified)

    @unittest.skipUnless(os.name == "posix", "flock fixture is POSIX-specific")
    def test_parallel_build_tree_contention_times_out_before_mutation(self):
        import fcntl

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.seed_stale_reports(root)
            environment = self.fixture(root)
            environment["OVERTE_JVM_COVERAGE_LOCK_TIMEOUT_SECONDS"] = "0.05"
            lock_path = Path(environment["OVERTE_JVM_COVERAGE_BUILD_DIR"] + ".lock")
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            with lock_path.open("a", encoding="utf-8") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                result = self.run_fixture(environment)
            self.assertEqual(1, result.returncode)
            self.assertIn("timed out waiting for standalone JVM coverage lock", result.stdout)
            self.assertEqual("stale", (root / "reports/report.xml").read_text())
            self.assertFalse((root / "tool-started").exists())

    def test_invalid_lock_timeout_changes_no_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.seed_stale_reports(root)
            environment = self.fixture(root)
            environment["OVERTE_JVM_COVERAGE_LOCK_TIMEOUT_SECONDS"] = "invalid"
            result = self.run_fixture(environment)
            self.assertEqual(2, result.returncode)
            self.assertIn("invalid standalone JVM coverage lock timeout", result.stdout)
            self.assertEqual("stale", (root / "reports/report.xml").read_text())
            self.assertFalse((root / "tool-started").exists())


if __name__ == "__main__":
    unittest.main()
