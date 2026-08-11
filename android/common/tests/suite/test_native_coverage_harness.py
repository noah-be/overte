import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest


ANDROID_ROOT = Path(__file__).resolve().parents[3]
RUNNER = ANDROID_ROOT / "common/tests/coverage/run-native-coverage.sh"


def executable(path: Path, content: str) -> None:
    path.write_text("#!/usr/bin/env bash\nset -euo pipefail\n" + content, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


class NativeCoverageHarnessTest(unittest.TestCase):
    def fixture(self, root: Path, fail_call: int = 0):
        cmake = root / "cmake"
        ctest = root / "ctest"
        gcovr = root / "gcovr"
        executable(cmake, "printf 'cmake\\n' >>\"$TOOL_LOG\"\n")
        executable(ctest, "printf 'ctest\\n' >>\"$TOOL_LOG\"\n")
        executable(gcovr, r'''
printf 'gcovr:%s\n' "$PWD" >>"$TOOL_LOG"
count=0
[[ -f "$GCOVR_COUNT" ]] && read -r count <"$GCOVR_COUNT"
count=$((count + 1))
printf '%s\n' "$count" >"$GCOVR_COUNT"
if [[ "${GCOVR_FAIL_CALL:-0}" == "$count" ]]; then exit 9; fi
xml=''
html=''
previous=''
for argument in "$@"; do
  [[ "$previous" == --xml ]] && xml="$argument"
  [[ "$previous" == --html-details ]] && html="$argument"
  previous="$argument"
done
if [[ "${GCOVR_MISSING_CALL:-0}" == "$count" ]]; then exit 0; fi
if [[ "${GCOVR_MALFORMED_CALL:-0}" == "$count" ]]; then
  printf '<broken\n' >"$xml"
  printf '<html>coverage</html>\n' >"$html"
  exit 0
fi
printf '<coverage line-rate="1" branch-rate="1"/>\n' >"$xml"
printf '<html>coverage</html>\n' >"$html"
''')
        return {
            **os.environ,
            "OVERTE_CMAKE_COMMAND": str(cmake),
            "OVERTE_CTEST_COMMAND": str(ctest),
            "OVERTE_GCOVR_COMMAND": str(gcovr),
            "OVERTE_NATIVE_COVERAGE_BUILD_DIR": str(root / "build"),
            "OVERTE_NATIVE_COVERAGE_REPORT_DIR": str(root / "reports"),
            "GCOVR_COUNT": str(root / "gcovr-count"),
            "GCOVR_FAIL_CALL": str(fail_call),
            "TOOL_LOG": str(root / "tool-log"),
        }

    @unittest.skipUnless(os.name == "posix", "flock fixture is POSIX-specific")
    def test_staging_failure_invalidates_old_reports_without_starting_tools(self):
        import fcntl

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reports = root / "reports"
            reports.mkdir()
            for name in (
                    "interface.xml", "login-state.xml", "pending-handoff.xml",
                    "interface.html", "interface.details.html",
                    "login-state.html", "pending-handoff.html"):
                (reports / name).write_text("stale", encoding="utf-8")
            failing_mktemp = root / "mktemp"
            executable(failing_mktemp, "exit 8\n")
            environment = self.fixture(root)
            environment["OVERTE_NATIVE_COVERAGE_MKTEMP_COMMAND"] = str(failing_mktemp)

            result = subprocess.run(
                [RUNNER], env=environment, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

            self.assertEqual(8, result.returncode, result.stdout)
            self.assertEqual([], list(reports.glob("*.xml")))
            self.assertEqual([], list(reports.glob("*.html")))
            self.assertEqual([], list(reports.glob(".native-coverage.*")))
            self.assertFalse((root / "tool-log").exists())
            lock_path = Path(environment["OVERTE_NATIVE_COVERAGE_BUILD_DIR"] + ".lock")
            with lock_path.open("a", encoding="utf-8") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def test_failure_invalidates_old_reports_and_cleans_staging(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reports = root / "reports"
            reports.mkdir()
            for name in ("interface.xml", "login-state.xml", "pending-handoff.xml"):
                (reports / name).write_text("stale", encoding="utf-8")
            result = subprocess.run([RUNNER], env=self.fixture(root, fail_call=2),
                                    text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            self.assertEqual(9, result.returncode)
            self.assertEqual([], list(reports.glob("*.xml")))
            self.assertEqual([], list(reports.glob(".native-coverage.*")))

    def test_success_publishes_all_reports_after_the_gates(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            environment = self.fixture(root)
            result = subprocess.run([RUNNER], env=environment,
                                    text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            self.assertEqual(0, result.returncode, result.stdout)
            reports = root / "reports"
            self.assertEqual(
                {"interface.xml", "login-state.xml", "pending-handoff.xml"},
                {path.name for path in reports.glob("*.xml")})
            self.assertEqual(3, len(list(reports.glob("*.html"))))
            self.assertEqual([], list(reports.glob(".native-coverage.*")))
            gcovr_calls = [line for line in Path(environment["TOOL_LOG"])
                           .read_text(encoding="utf-8").splitlines()
                           if line.startswith("gcovr:")]
            self.assertEqual([f"gcovr:{ANDROID_ROOT.parent}"] * 3, gcovr_calls)

    @unittest.skipUnless(os.name == "posix", "flock fixture is POSIX-specific")
    def test_success_status_without_a_required_output_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            environment = self.fixture(root)
            environment["GCOVR_MISSING_CALL"] = "2"
            result = subprocess.run(
                [RUNNER], env=environment, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

            self.assertEqual(1, result.returncode, result.stdout)
            self.assertIn("produced no login-state.xml report", result.stdout)
            self.assertEqual([], list((root / "reports").glob("*.xml")))
            self.assertEqual([], list((root / "reports").glob("*.html")))
            self.assertEqual([], list((root / "reports").glob(".native-coverage.*")))
            lock_path = Path(environment["OVERTE_NATIVE_COVERAGE_BUILD_DIR"] + ".lock")
            import fcntl
            with lock_path.open("a", encoding="utf-8") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def test_malformed_coverage_xml_is_rejected_before_publication(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            environment = self.fixture(root)
            environment["GCOVR_MALFORMED_CALL"] = "2"
            result = subprocess.run(
                [RUNNER], env=environment, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

            self.assertEqual(1, result.returncode, result.stdout)
            self.assertIn("invalid native coverage XML", result.stdout)
            self.assertEqual([], list((root / "reports").glob("*.xml")))
            self.assertEqual([], list((root / "reports").glob("*.html")))
            self.assertEqual([], list((root / "reports").glob(".native-coverage.*")))

    @unittest.skipUnless(os.name == "posix", "flock fixture is POSIX-specific")
    def test_parallel_build_tree_contention_times_out_cleanly(self):
        import fcntl

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            environment = self.fixture(root)
            environment["OVERTE_NATIVE_COVERAGE_LOCK_TIMEOUT_SECONDS"] = "0.05"
            lock_path = Path(environment["OVERTE_NATIVE_COVERAGE_BUILD_DIR"] + ".lock")
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            with lock_path.open("a", encoding="utf-8") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                result = subprocess.run(
                    [RUNNER], env=environment, text=True,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            self.assertEqual(1, result.returncode)
            self.assertIn("timed out waiting for native coverage lock", result.stdout)


if __name__ == "__main__":
    unittest.main()
