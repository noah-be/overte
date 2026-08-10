#!/usr/bin/env python3
import importlib.util
import os
from pathlib import Path
import signal
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
import unittest
from unittest import mock


MODULE_PATH = Path(__file__).with_name("run-order-isolation-audit.py")
SPEC = importlib.util.spec_from_file_location("overte_stability", MODULE_PATH)
audit = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = audit
assert SPEC.loader is not None
SPEC.loader.exec_module(audit)


class StabilityRunnerTest(unittest.TestCase):
    def test_exit_vs_kill_race_is_already_terminated(self):
        with mock.patch.object(audit.os, "killpg", side_effect=ProcessLookupError):
            self.assertFalse(audit.kill_process_group(12345, signal.SIGTERM))

    def test_seeded_orders_are_stable_and_distinct(self):
        first = [name for name, _ in audit.serial_order(0)]
        second = [name for name, _ in audit.serial_order(1)]
        self.assertEqual(["native", "native-endurance", "asset-cache", "js-endurance", "mutations", "deep-links", "javascript"], first)
        self.assertEqual(["javascript", "asset-cache", "mutations", "deep-links", "native", "native-endurance", "js-endurance"], second)
        self.assertNotEqual(first, second)

    def test_replica_paths_are_private(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            _, first = audit.case_invocation(("native", ["true"]), workspace, "one")
            _, second = audit.case_invocation(("native", ["true"]), workspace, "two")
            mutation_one, _ = audit.case_invocation(("mutations", ["true"]), workspace, "one")
            mutation_two, _ = audit.case_invocation(("mutations", ["true"]), workspace, "two")
            self.assertTrue(Path(first["TMPDIR"]).is_dir())
            self.assertTrue(Path(second["TMPDIR"]).is_dir())
        self.assertNotEqual(first["OVERTE_NATIVE_TEST_BUILD_DIR"], second["OVERTE_NATIVE_TEST_BUILD_DIR"])
        self.assertNotEqual(first["OVERTE_TEST_REPORT_DIR"], second["OVERTE_TEST_REPORT_DIR"])
        self.assertNotEqual(first["TMPDIR"], second["TMPDIR"])
        self.assertTrue(Path(first["TMPDIR"]).is_relative_to(workspace))
        self.assertTrue(Path(second["TMPDIR"]).is_relative_to(workspace))
        self.assertNotEqual(mutation_one[-1], mutation_two[-1])

    def test_parallel_cases_really_overlap(self):
        case = ("overlap", ["python3", "-c", "import time; time.sleep(0.35)"])
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            started = time.monotonic()
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [executor.submit(audit.run_case, case, workspace, str(index)) for index in range(2)]
                for future in futures:
                    future.result()
            elapsed = time.monotonic() - started
        self.assertLess(elapsed, 0.65)

    def test_failure_is_red_and_workspace_is_cleaned(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            with self.assertRaisesRegex(RuntimeError, "failed with 23"):
                audit.run_case(("fixture", ["python3", "-c", "raise SystemExit(23)"]), workspace, "failure")
        self.assertFalse(workspace.exists())

    def test_timeout_terminates_process_group(self):
        environment = dict(os.environ)
        with tempfile.TemporaryDirectory() as temporary:
            pid_file = Path(temporary) / "child.pid"
            program = (
                "import pathlib,signal,subprocess,time; "
                "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
                "p=subprocess.Popen(['python3','-c','import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(60)']); "
                f"pathlib.Path({str(pid_file)!r}).write_text(str(p.pid)); time.sleep(60)"
            )
            with self.assertRaisesRegex(RuntimeError, "timed out"):
                audit.run_process(["python3", "-c", program], environment, timeout=0.3)
            child_pid = int(pid_file.read_text())
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline and Path(f"/proc/{child_pid}").exists():
                time.sleep(0.02)
            self.assertFalse(Path(f"/proc/{child_pid}").exists(), "timed-out child survived process-group kill")

    def test_timeout_preserves_separate_stdout_and_stderr(self):
        program = (
            "import sys,time; "
            "print('stdout-before-timeout', flush=True); "
            "print('stderr-before-timeout', file=sys.stderr, flush=True); "
            "time.sleep(60)"
        )
        with self.assertRaises(RuntimeError) as raised:
            audit.run_process(["python3", "-c", program], dict(os.environ), timeout=0.1)
        self.assertIn("stdout-before-timeout", str(raised.exception))
        self.assertIn("stderr-before-timeout", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
