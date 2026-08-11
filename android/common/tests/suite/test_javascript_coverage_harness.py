import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest


ANDROID_ROOT = Path(__file__).resolve().parents[3]
RUNNER = ANDROID_ROOT / "common/tests/coverage/run-javascript-coverage.sh"


def executable(path: Path, content: str) -> None:
    path.write_text("#!/usr/bin/env bash\nset -euo pipefail\n" + content,
                    encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


class JavaScriptCoverageHarnessTest(unittest.TestCase):
    def fixture(self, root: Path, body: str):
        npm = root / "npm"
        executable(npm, body)
        return {
            **os.environ,
            "OVERTE_JAVASCRIPT_COVERAGE_REPORT_DIR": str(root / "reports"),
            "OVERTE_NPM_COMMAND": str(npm),
            "NPM_MARKER": str(root / "npm-started"),
        }

    def run_runner(self, environment):
        return subprocess.run(
            [RUNNER], env=environment, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

    def test_success_publishes_complete_summary_and_console_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = self.run_runner(self.fixture(
                root, "printf started >\"$NPM_MARKER\"\nprintf 'complete coverage\\n'\n"))

            self.assertEqual(0, result.returncode, result.stdout)
            self.assertEqual("complete coverage\n", result.stdout)
            self.assertEqual(
                "complete coverage\n",
                (root / "reports/summary.txt").read_text(encoding="utf-8"))
            self.assertEqual([], list((root / "reports").glob(".summary.txt.????????")))

    def test_failure_invalidates_stale_summary_and_preserves_status(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reports = root / "reports"
            reports.mkdir()
            (reports / "summary.txt").write_text("stale", encoding="utf-8")
            result = self.run_runner(self.fixture(
                root, "printf started >\"$NPM_MARKER\"\nprintf 'partial\\n'\nexit 7\n"))

            self.assertEqual(7, result.returncode, result.stdout)
            self.assertEqual("partial\n", result.stdout)
            self.assertFalse((reports / "summary.txt").exists())
            self.assertEqual([], list(reports.glob(".summary.txt.????????")))

    def test_symlink_is_rejected_before_npm_starts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reports = root / "reports"
            reports.mkdir()
            victim = root / "victim"
            victim.write_text("safe", encoding="utf-8")
            (reports / "summary.txt").symlink_to(victim)
            result = self.run_runner(self.fixture(
                root, "printf started >\"$NPM_MARKER\"\n"))

            self.assertEqual(1, result.returncode, result.stdout)
            self.assertIn("cannot be a symlink", result.stdout)
            self.assertEqual("safe", victim.read_text(encoding="utf-8"))
            self.assertTrue((reports / "summary.txt").is_symlink())
            self.assertFalse((root / "npm-started").exists())

    @unittest.skipUnless(os.name == "posix", "flock fixture is POSIX-specific")
    def test_lock_timeout_preserves_stale_summary_without_starting_npm(self):
        import fcntl

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reports = root / "reports"
            reports.mkdir()
            summary = reports / "summary.txt"
            summary.write_text("stale", encoding="utf-8")
            environment = self.fixture(root, "printf started >\"$NPM_MARKER\"\n")
            environment["OVERTE_JAVASCRIPT_COVERAGE_LOCK_TIMEOUT_SECONDS"] = "0.05"
            with (reports / ".summary.txt.lock").open("a", encoding="utf-8") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                result = self.run_runner(environment)

            self.assertEqual(1, result.returncode, result.stdout)
            self.assertIn("timed out waiting for JavaScript coverage lock", result.stdout)
            self.assertEqual("stale", summary.read_text(encoding="utf-8"))
            self.assertFalse((root / "npm-started").exists())


if __name__ == "__main__":
    unittest.main()
