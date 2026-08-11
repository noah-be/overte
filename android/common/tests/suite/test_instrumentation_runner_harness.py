import os
from pathlib import Path
import stat
import subprocess
import tempfile
import time
import unittest


ANDROID_ROOT = Path(__file__).resolve().parents[3]
RUNNER = ANDROID_ROOT / "common/tests/android/run-instrumentation-tests.sh"


def executable(path: Path, content: str) -> None:
    path.write_text("#!/usr/bin/env bash\nset -euo pipefail\n" + content,
                    encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


class InstrumentationRunnerHarnessTest(unittest.TestCase):
    def fixture(self, root: Path, gradle_body: str):
        gradle = root / "gradlew"
        executable(gradle, gradle_body)
        return {
            **os.environ,
            "PHONE_DEVICE_LOCK_FILE": str(root / "phone-device.lock"),
            "PHONE_DEVICE_LOCK_RELEASE_DELAY_SECONDS": "0",
            "OVERTE_INSTRUMENTATION_GRADLEW_COMMAND": str(gradle),
        }

    @staticmethod
    def wait_for(path: Path, process: subprocess.Popen, timeout=3.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if path.exists():
                return
            if process.poll() is not None:
                raise AssertionError(
                    f"process exited before {path.name}: {process.returncode}")
            time.sleep(0.01)
        raise AssertionError(f"timed out waiting for {path}")

    def test_parallel_runners_serialize_the_full_gradle_lifecycle(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            environment = self.fixture(root, r'''
printf started >"$MARKER"
if [[ "${RUN_ID:-}" == first ]]; then
    while [[ ! -f "$RELEASE_FIRST" ]]; do sleep 0.01; done
fi
''')
            release = root / "release-first"
            first_marker = root / "first-started"
            second_marker = root / "second-started"
            first_env = {
                **environment, "RUN_ID": "first", "MARKER": str(first_marker),
                "RELEASE_FIRST": str(release)}
            second_env = {
                **environment, "RUN_ID": "second", "MARKER": str(second_marker),
                "RELEASE_FIRST": str(release)}
            first = subprocess.Popen(
                [RUNNER], env=first_env, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            try:
                self.wait_for(first_marker, first)
                second = subprocess.Popen(
                    [RUNNER], env=second_env, text=True,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                try:
                    time.sleep(0.1)
                    self.assertFalse(second_marker.exists())
                    release.write_text("release", encoding="utf-8")
                    first_output = first.communicate(timeout=3)[0]
                    second_output = second.communicate(timeout=3)[0]
                    self.assertEqual(0, first.returncode, first_output)
                    self.assertEqual(0, second.returncode, second_output)
                    self.assertTrue(second_marker.exists())
                finally:
                    if second.poll() is None:
                        second.kill()
                        second.wait()
            finally:
                if first.poll() is None:
                    first.kill()
                    first.wait()
            self.assertFalse((root / "phone-device.lock.owner").exists())

    def test_gradle_status_is_preserved_and_lock_is_released(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            environment = self.fixture(root, "exit 23\n")
            result = subprocess.run(
                [RUNNER], env=environment, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            self.assertEqual(23, result.returncode, result.stdout)
            self.assertFalse((root / "phone-device.lock.owner").exists())

    def test_existing_lock_scope_runs_gradle_directly(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            marker = root / "gradle-started"
            environment = self.fixture(
                root, 'printf started >"$DIRECT_MARKER"\n')
            environment["PHONE_DEVICE_LOCK_HELD"] = "1"
            environment["DIRECT_MARKER"] = str(marker)
            # An unusable lock path proves that the direct path does not try
            # to acquire the lock recursively.
            environment["PHONE_DEVICE_LOCK_FILE"] = str(root / "missing/lock")
            result = subprocess.run(
                [RUNNER], env=environment, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            self.assertEqual(0, result.returncode, result.stdout)
            self.assertTrue(marker.exists())


if __name__ == "__main__":
    unittest.main()
