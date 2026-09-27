#!/usr/bin/env python3
"""Black-box contracts for bounded, complete unittest worker execution."""

from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest


RUNNER = Path(__file__).with_name("run-unittest-suite.py")


@unittest.skipUnless(sys.platform.startswith("linux"), "parallel workers use Linux child subreaping")
class UnittestRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="overte-unittest-regression-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.tests = self.root / "selected"
        self.tests.mkdir()

    def write(self, name, source):
        target = self.tests / name
        target.write_text(textwrap.dedent(source), encoding="utf-8")
        return target

    def run_cli(self, *arguments):
        return subprocess.run([sys.executable, str(RUNNER), str(self.tests), *arguments],
                              cwd=self.root, text=True, capture_output=True, timeout=15)

    def test_empty_import_failure_and_invalid_limits_are_failures(self):
        for arguments in ((), ("--jobs", "2")):
            result = self.run_cli(*arguments)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("no test cases", result.stderr)
        self.write("test_broken.py", "import absent_overte_runner_regression_module\n")
        result = self.run_cli("--jobs", "2")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("absent_overte_runner_regression_module", result.stderr)
        for arguments in (("--jobs", "0"), ("--jobs", "9"),
                          ("--timeout-seconds", "0"), ("--timeout-seconds", "1801")):
            with self.subTest(arguments=arguments):
                self.assertEqual(self.run_cli(*arguments).returncode, 2)

    def test_serial_default_and_workers_keep_working_directory_and_discovery_imports(self):
        (self.root / "repository_helper.py").write_text("VALUE = 40\n")
        (self.tests / "local_helper.py").write_text("VALUE = 2\n")
        self.write("test_imports.py", """
            import unittest
            from repository_helper import VALUE as REPOSITORY
            from local_helper import VALUE as LOCAL
            class Imports(unittest.TestCase):
                def test_helpers(self):
                    self.assertEqual(REPOSITORY + LOCAL, 42)
        """)
        for arguments in ((), ("--jobs", "2")):
            with self.subTest(arguments=arguments):
                result = self.run_cli(*arguments)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("Ran 1 test", result.stderr)

    def test_modules_run_concurrently_with_bounded_workers_and_intact_fixtures(self):
        # The rendezvous proves overlap rather than relying on wall-clock speed.
        # A file lock makes the peak worker count an independent observation.
        (self.root / "shared_fixture.py").write_text(textwrap.dedent("""
            import fcntl
            import json
            from pathlib import Path
            def update(delta):
                with open('counts.lock', 'a') as lock:
                    fcntl.flock(lock, fcntl.LOCK_EX)
                    path = Path('counts.json')
                    value = json.loads(path.read_text()) if path.exists() else {'active': 0, 'peak': 0}
                    value['active'] += delta
                    value['peak'] = max(value['peak'], value['active'])
                    path.write_text(json.dumps(value))
        """))
        for index in range(4):
            self.write(f"test_{index}.py", f"""
                import os
                from pathlib import Path
                import time
                import unittest
                from shared_fixture import update
                setup_count = 0
                def setUpModule():
                    global setup_count
                    setup_count += 1
                    update(1)
                    Path('started-{index}').write_text(str(os.getpid()))
                def tearDownModule():
                    update(-1)
                    Path('finished-{index}').write_text('done')
                class Fixture(unittest.TestCase):
                    @classmethod
                    def setUpClass(cls):
                        cls.calls = 0
                    def test_01_rendezvous(self):
                        self.assertEqual(setup_count, 1)
                        if {index} < 2:
                            deadline = time.monotonic() + 3
                            while not Path('started-{1 - index}').exists():
                                self.assertLess(time.monotonic(), deadline, 'workers did not overlap')
                                time.sleep(0.01)
                        time.sleep(0.08)
                        type(self).calls += 1
                    def test_02_same_fixture(self):
                        self.assertEqual(setup_count, 1)
                        self.assertEqual(type(self).calls, 1)
            """)
        report_path = self.root / "run.json"
        result = self.run_cli("--jobs", "2", "--timeout-seconds", "5", "--report-json", str(report_path))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads((self.root / "counts.json").read_text()), {"active": 0, "peak": 2})
        self.assertEqual(len(list(self.root.glob("finished-*"))), 4)
        self.assertEqual(len({path.read_text() for path in self.root.glob("started-*")}), 4)
        self.assertIn("selected=8, loaded=8, ran=8", result.stderr)
        report = json.loads(report_path.read_text())
        selected = [identifier for module in report["modules"] for identifier in module["selected_ids"]]
        loaded = [identifier for module in report["modules"] for identifier in module["result"]["loaded_ids"]]
        expected = [f"test_{index}.Fixture.{method}" for index in range(4)
                    for method in ("test_01_rendezvous", "test_02_same_fixture")]
        self.assertEqual(selected, expected)
        self.assertEqual(loaded, expected)
        self.assertEqual([identifier for module in report["modules"]
                          for identifier in module["result"]["executed_ids"]], expected)
        self.assertEqual(report["ran"], 8)
        positions = [result.stderr.index(f"=== test_{index} ") for index in range(4)]
        self.assertEqual(positions, sorted(positions), "completion order must not reorder reports")

    def test_assertion_failure_does_not_hide_other_modules_or_cases(self):
        self.write("test_a_failed.py", """
            import unittest
            class Failed(unittest.TestCase):
                def test_failure(self):
                    self.fail('worker-assertion-canary')
                def test_later_case(self):
                    pass
        """)
        self.write("test_z_passed.py", """
            from pathlib import Path
            import unittest
            class Passed(unittest.TestCase):
                def test_result(self):
                    Path('survived').touch()
        """)
        result = self.run_cli("--jobs", "2")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("worker-assertion-canary", result.stderr)
        self.assertIn("selected=3, loaded=3, ran=3", result.stderr)
        self.assertTrue((self.root / "survived").exists())

    def test_worker_crash_or_zero_exit_without_results_cannot_pass(self):
        self.write("test_z_passed.py", """
            from pathlib import Path
            import unittest
            class Passed(unittest.TestCase):
                def test_result(self):
                    Path('survived').touch()
        """)
        for code in (7, 0):
            with self.subTest(code=code):
                self.write("test_a_crashed.py", f"""
                    import os
                    import unittest
                    class Crashed(unittest.TestCase):
                        def test_exit(self):
                            os._exit({code})
                """)
                # The two fixture edits can share timestamp/size; remove cached
                # bytecode so this test actually exercises both exit statuses.
                for cached in (self.tests / "__pycache__").glob("test_a_crashed.*.pyc"):
                    cached.unlink()
                (self.root / "survived").unlink(missing_ok=True)
                result = self.run_cli("--jobs", "2")
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertIn("missing or invalid worker result", result.stderr)
                self.assertIn(f"exit code {code}", result.stderr)
                self.assertTrue((self.root / "survived").exists())

    def test_worker_loaded_ids_must_match_discovery(self):
        self.write("test_changed.py", """
            from pathlib import Path
            import unittest
            marker = Path('already-imported')
            imported_again = marker.exists()
            marker.touch()
            class Changed(unittest.TestCase):
                def id(self):
                    return super().id() + ('_different' if imported_again else '')
                def test_selected(self):
                    Path('unexpected-execution').touch()
        """)
        result = self.run_cli("--jobs", "2")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("loaded test IDs differ from discovery", result.stderr)
        self.assertFalse((self.root / "unexpected-execution").exists())

    def test_early_successful_stop_cannot_omit_selected_cases(self):
        self.write("test_stopped.py", """
            from pathlib import Path
            import unittest
            class Stopped(unittest.TestCase):
                def test_01_stop(self):
                    self._outcome.result.stop()
                def test_02_missing(self):
                    Path('should-have-executed').touch()
        """)
        result = self.run_cli("--jobs", "2")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("not completely executed or explicitly skipped", result.stderr)
        self.assertIn("selected=2, loaded=2, ran=1", result.stderr)

    def test_failed_discovery_removes_previous_success_report(self):
        report = self.root / "run.json"
        report.write_text('{"successful": true}\n')
        result = self.run_cli("--jobs", "2", "--report-json", str(report))
        self.assertNotEqual(result.returncode, 0, result.stderr)
        self.assertFalse(report.exists())

    def test_runtime_fixture_skips_account_for_each_selected_case(self):
        self.write("test_module_skip.py", """
            import unittest
            def setUpModule():
                raise unittest.SkipTest('skip module fixture')
            class Skipped(unittest.TestCase):
                def test_one(self):
                    self.fail('must not execute')
                def test_two(self):
                    self.fail('must not execute')
        """)
        self.write("test_class_skip.py", """
            import unittest
            class Skipped(unittest.TestCase):
                @classmethod
                def setUpClass(cls):
                    raise unittest.SkipTest('skip class fixture')
                def test_one(self):
                    self.fail('must not execute')
                def test_two(self):
                    self.fail('must not execute')
        """)
        report_path = self.root / "run.json"
        result = self.run_cli("--jobs", "2", "--report-json", str(report_path))
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(report_path.read_text())
        self.assertEqual(report["selected"], 4)
        self.assertEqual(report["ran"], 0)
        self.assertEqual(sum(len(module["result"]["fixture_skipped_ids"])
                             for module in report["modules"]), 4)

    def test_module_fixture_failure_and_skips_keep_unittest_semantics(self):
        self.write("test_skipped.py", """
            import unittest
            @unittest.skip('fixture skip')
            class Skipped(unittest.TestCase):
                def test_skipped(self):
                    self.fail('must not execute')
            class Ordinary(unittest.TestCase):
                @unittest.expectedFailure
                def test_known_failure(self):
                    self.fail('known failure')
        """)
        passed = self.run_cli("--jobs", "2")
        self.assertEqual(passed.returncode, 0, passed.stderr)
        self.assertIn("selected=2, loaded=2, ran=2, skipped=1", passed.stderr)
        self.write("test_broken_fixture.py", """
            import unittest
            def setUpModule():
                raise RuntimeError('module-fixture-canary')
            class Broken(unittest.TestCase):
                def test_selected(self):
                    pass
        """)
        failed = self.run_cli("--jobs", "2")
        self.assertEqual(failed.returncode, 1, failed.stderr)
        self.assertIn("module-fixture-canary", failed.stderr)
        self.assertIn("selected=3, loaded=3, ran=2", failed.stderr)

    def descendant_fixture(self, finish=False, detached=False):
        self.write("test_a_descendant.py", f"""
            from pathlib import Path
            import os
            import signal
            import subprocess
            import sys
            import time
            import unittest
            class Descendant(unittest.TestCase):
                def test_child(self):
                    signal.signal(signal.SIGTERM, signal.SIG_IGN)
                    child = subprocess.Popen([sys.executable, '-c',
                        'import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(30)'],
                        start_new_session={detached!r})
                    Path('processes.json').write_text(__import__('json').dumps([os.getpid(), child.pid]))
                    if not {finish!r}:
                        time.sleep(30)
        """)
        self.write("test_z_other.py", """
            from pathlib import Path
            import unittest
            class Other(unittest.TestCase):
                def test_survives(self):
                    Path('survived').touch()
        """)

    @staticmethod
    def alive(pid):
        # Orphans may briefly be zombies until the container's init reaps them.
        status = Path(f"/proc/{pid}/stat")
        if status.exists():
            try:
                return status.read_text().split(") ", 1)[1].split()[0] != "Z"
            except FileNotFoundError:
                return False
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        return True

    def assert_processes_stopped(self, processes):
        deadline = time.monotonic() + 2
        while any(self.alive(pid) for pid in processes) and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertEqual([pid for pid in processes if self.alive(pid)], [])

    def kill_fixture_processes(self):
        path = self.root / "processes.json"
        if path.exists():
            for pid in json.loads(path.read_text()):
                try:
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass

    def test_worker_timeout_kills_descendants_and_continues_other_modules(self):
        self.addCleanup(self.kill_fixture_processes)
        for detached in (False, True):
            with self.subTest(detached=detached):
                self.descendant_fixture(detached=detached)
                started = time.monotonic()
                result = self.run_cli("--jobs", "2", "--timeout-seconds", "1")
                self.assertLess(time.monotonic() - started, 5)
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertIn("worker timed out after 1s", result.stderr)
                self.assertTrue((self.root / "survived").exists())
                self.assert_processes_stopped(json.loads((self.root / "processes.json").read_text()))

    def test_successful_worker_cannot_leave_a_background_descendant(self):
        self.addCleanup(self.kill_fixture_processes)
        for detached in (False, True):
            with self.subTest(detached=detached):
                self.descendant_fixture(finish=True, detached=detached)
                result = self.run_cli("--jobs", "2", "--timeout-seconds", "5")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assert_processes_stopped(json.loads((self.root / "processes.json").read_text()))

    def test_interrupt_stops_workers_and_descendants_before_returning(self):
        self.descendant_fixture(detached=True)
        self.addCleanup(self.kill_fixture_processes)
        report = self.root / "run.json"
        report.write_text('{"successful": true}\n')
        with (self.root / "interrupt.log").open("w+") as output:
            process = subprocess.Popen([
                sys.executable, str(RUNNER), str(self.tests), "--jobs", "2", "--report-json", str(report),
            ], cwd=self.root, stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
            try:
                deadline = time.monotonic() + 5
                marker = self.root / "processes.json"
                while not marker.exists() and process.poll() is None and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertTrue(marker.exists(), "worker never reached the fixture")
                process.send_signal(signal.SIGTERM)
                self.assertEqual(process.wait(timeout=4), 128 + signal.SIGTERM)
                self.assertFalse(report.exists())
                self.assert_processes_stopped(json.loads(marker.read_text()))
            finally:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGKILL)
                process.wait()

    def test_adopted_daemon_survives_until_all_workers_finish_then_is_reaped(self):
        self.addCleanup(self.kill_fixture_processes)
        daemon = "import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(30)"
        intermediate = (
            "import json,subprocess,sys; from pathlib import Path; "
            f"child=subprocess.Popen([sys.executable, '-c', {daemon!r}], start_new_session=True); "
            "Path('processes.json').write_text(json.dumps([child.pid]))"
        )
        self.write("test_a_producer.py", f"""
            import subprocess
            import sys
            import unittest
            class Producer(unittest.TestCase):
                def test_start(self):
                    subprocess.run([sys.executable, '-c', {intermediate!r}], check=True)
        """)
        self.write("test_b_consumer.py", """
            import json
            import os
            from pathlib import Path
            import time
            import unittest
            class Consumer(unittest.TestCase):
                def test_daemon(self):
                    deadline = time.monotonic() + 3
                    marker = Path('processes.json')
                    while not marker.exists():
                        self.assertLess(time.monotonic(), deadline)
                        time.sleep(0.01)
                    time.sleep(0.25)
                    os.kill(json.loads(marker.read_text())[0], 0)
        """)
        result = self.run_cli("--jobs", "2", "--timeout-seconds", "5")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_processes_stopped(json.loads((self.root / "processes.json").read_text()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
