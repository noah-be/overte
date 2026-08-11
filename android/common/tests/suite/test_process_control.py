import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock


TESTS_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TESTS_ROOT))
import process_control  # noqa: E402 -- controlled tests path


class ProcessControlTest(unittest.TestCase):
    def test_normal_process_preserves_separate_streams(self):
        process = subprocess.Popen(
            [sys.executable, "-c",
             "import sys; print('out'); print('err', file=sys.stderr)"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            **process_control.popen_session_kwargs())
        stdout, stderr = process_control.communicate_with_timeout(
            process, 5, termination_grace=0.1)
        self.assertEqual("out\n", stdout)
        self.assertEqual("err\n", stderr)
        self.assertEqual(0, process.returncode)

    def test_exit_vs_group_signal_race_is_tolerated(self):
        with mock.patch.object(process_control.os, "killpg", side_effect=ProcessLookupError):
            self.assertFalse(process_control.kill_process_group(12345, signal.SIGTERM))

    @unittest.skipUnless(os.name == "posix", "process-group cleanup is POSIX-specific")
    def test_timeout_sweeps_term_resistant_parent_and_child_and_keeps_output(self):
        with tempfile.TemporaryDirectory() as directory:
            child_pid_file = Path(directory) / "child.pid"
            child = (
                "import os,signal,time;"
                f"open({str(child_pid_file)!r},'w').write(str(os.getpid()));"
                "signal.signal(signal.SIGTERM,signal.SIG_IGN);"
                "os.close(1);os.close(2);time.sleep(60)"
            )
            parent = (
                "import signal,subprocess,sys,time;"
                "signal.signal(signal.SIGTERM,signal.SIG_IGN);"
                f"subprocess.Popen([sys.executable,'-c',{child!r}]);"
                "print('before-timeout',flush=True);time.sleep(60)"
            )
            process = subprocess.Popen(
                [sys.executable, "-c", parent], text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                **process_control.popen_session_kwargs())
            with self.assertRaises(subprocess.TimeoutExpired) as raised:
                process_control.communicate_with_timeout(
                    process, 0.3, termination_grace=0.2)
            self.assertIn("before-timeout", raised.exception.output)
            child_pid = int(child_pid_file.read_text(encoding="utf-8"))
            deadline = time.monotonic() + 2
            while Path(f"/proc/{child_pid}").exists() and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertFalse(Path(f"/proc/{child_pid}").exists())


if __name__ == "__main__":
    unittest.main()
