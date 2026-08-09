import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest


ANDROID_ROOT = Path(__file__).resolve().parents[2]
RUNNER = ANDROID_ROOT / "tests/robolectric/run-tests.sh"


def executable(path: Path, content: str) -> None:
    path.write_text("#!/usr/bin/env bash\nset -euo pipefail\n" + content,
                    encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


class RobolectricRunnerHarnessTest(unittest.TestCase):
    def fixture(self, root: Path, java_major: int, gradle_body: str):
        java_home = root / "jdk"
        java_home.mkdir()
        executable(java_home / "java", "exit 99\n")
        (java_home / "bin").mkdir()
        executable(
            java_home / "bin/java",
            f'printf \'openjdk version "{java_major}.0.1"\\n\' >&2\n'
            'printf java >"$JAVA_MARKER"\n')
        gradle = root / "gradlew"
        executable(gradle, gradle_body)
        return {
            **os.environ,
            "OVERTE_ROBOLECTRIC_REPORT_DIR": str(root / "reports"),
            "OVERTE_ROBOLECTRIC_LOCK_FILE": str(root / "robolectric.lock"),
            "OVERTE_ROBOLECTRIC_JAVA_HOME": str(java_home),
            "OVERTE_GRADLEW_COMMAND": str(gradle),
            "JAVA_MARKER": str(root / "java-started"),
            "GRADLE_MARKER": str(root / "gradle-started"),
            "REPORT_DIR": str(root / "reports"),
        }

    def run_runner(self, environment):
        return subprocess.run(
            [RUNNER], env=environment, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

    @staticmethod
    def seed_stale(root: Path):
        reports = root / "reports"
        reports.mkdir()
        report = reports / "TEST-stale.xml"
        report.write_text("stale", encoding="utf-8")
        return report

    def test_wrong_java_invalidates_stale_report_without_gradle(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stale = self.seed_stale(root)
            environment = self.fixture(
                root, 17, 'printf gradle >"$GRADLE_MARKER"\n')
            result = self.run_runner(environment)

            self.assertEqual(2, result.returncode, result.stdout)
            self.assertFalse(stale.exists())
            self.assertTrue((root / "java-started").exists())
            self.assertFalse((root / "gradle-started").exists())

    def test_gradle_failure_invalidates_stale_report_and_preserves_status(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stale = self.seed_stale(root)
            environment = self.fixture(
                root, 21, 'printf gradle >"$GRADLE_MARKER"\nexit 7\n')
            result = self.run_runner(environment)

            self.assertEqual(7, result.returncode, result.stdout)
            self.assertFalse(stale.exists())
            self.assertTrue((root / "gradle-started").exists())

    def test_success_without_fresh_reports_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            environment = self.fixture(
                root, 21, 'printf gradle >"$GRADLE_MARKER"\n')
            result = self.run_runner(environment)

            self.assertEqual(1, result.returncode, result.stdout)
            self.assertIn("no fresh JUnit reports", result.stdout)

    def test_malformed_and_zero_test_reports_are_rejected(self):
        fixtures = (
            ("malformed", "<testsuite", "invalid Robolectric JUnit output"),
            ("zero", '<testsuite tests="0" failures="0" errors="0" skipped="0"/>',
             "contain no tests"),
        )
        for label, report, message in fixtures:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                environment = self.fixture(
                    root, 21,
                    f'printf \'%s\\n\' \'{report}\' >"$REPORT_DIR/TEST-result.xml"\n')
                result = self.run_runner(environment)

                self.assertEqual(1, result.returncode, result.stdout)
                self.assertIn(message, result.stdout)

    def test_positive_reports_are_accepted_including_testsuites_aggregate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            environment = self.fixture(
                root, 21,
                "printf '%s\\n' '<testsuite tests=\"2\" failures=\"0\" "
                "errors=\"0\" skipped=\"0\"/>' >\"$REPORT_DIR/TEST-one.xml\"\n"
                "printf '%s\\n' '<testsuites><testsuite tests=\"3\" failures=\"1\" "
                "errors=\"0\" skipped=\"1\"/></testsuites>' "
                ">\"$REPORT_DIR/TEST-two.xml\"\n")
            result = self.run_runner(environment)

            self.assertEqual(0, result.returncode, result.stdout)

    @unittest.skipUnless(os.name == "posix", "flock fixture is POSIX-specific")
    def test_lock_timeout_preserves_stale_report_and_starts_no_tools(self):
        import fcntl

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stale = self.seed_stale(root)
            environment = self.fixture(
                root, 21, 'printf gradle >"$GRADLE_MARKER"\n')
            environment["OVERTE_ROBOLECTRIC_LOCK_TIMEOUT_SECONDS"] = "0.05"
            with (root / "robolectric.lock").open("a", encoding="utf-8") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                result = self.run_runner(environment)

            self.assertEqual(2, result.returncode, result.stdout)
            self.assertTrue(stale.exists())
            self.assertFalse((root / "java-started").exists())
            self.assertFalse((root / "gradle-started").exists())

    def test_invalid_timeout_preserves_stale_report_and_starts_no_tools(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stale = self.seed_stale(root)
            environment = self.fixture(
                root, 21, 'printf gradle >"$GRADLE_MARKER"\n')
            environment["OVERTE_ROBOLECTRIC_LOCK_TIMEOUT_SECONDS"] = "never"
            result = self.run_runner(environment)

            self.assertEqual(2, result.returncode, result.stdout)
            self.assertTrue(stale.exists())
            self.assertFalse((root / "java-started").exists())
            self.assertFalse((root / "gradle-started").exists())


if __name__ == "__main__":
    unittest.main()
