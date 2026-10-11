"""Exercise detached fixture cleanup against actual host processes."""
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fixture.owned_processes import OwnedProcesses, OWNER_VARIABLE


@unittest.skipUnless(sys.platform.startswith("linux"), "Linux descendant tracking")
class OwnedFixtureProcessesTest(unittest.TestCase):
    def test_exited_parent_and_detached_child_are_reaped_without_foreign_process(self):
        with tempfile.TemporaryDirectory() as temporary:
            environment = os.environ.copy()
            environment["XDG_CONFIG_HOME"] = temporary
            owner = OwnedProcesses(environment)
            pid_file = Path(temporary) / "child.pid"
            program = (
                "import os,sys,time,pathlib; pid=os.fork(); "
                "\nif pid: sys.exit(0)"
                "\nos.setsid(); pathlib.Path(sys.argv[1]).write_text(str(os.getpid())); "
                "time.sleep(60)"
            )
            foreign_environment = environment.copy()
            foreign_environment[OWNER_VARIABLE] = "foreign-owner"
            foreign = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"],
                                       env=foreign_environment)
            parent = subprocess.Popen([sys.executable, "-c", program, str(pid_file)],
                                      env=environment)
            child = None
            try:
                parent.wait(timeout=5)
                deadline = time.monotonic() + 5
                while not pid_file.exists() and time.monotonic() < deadline:
                    time.sleep(0.02)
                self.assertTrue(pid_file.exists())
                child = int(pid_file.read_text())
                self.assertEqual(child, os.getsid(child))
                self.assertTrue(owner.matches(child))
                self.assertFalse(owner.matches(foreign.pid))
                owner.stop(grace_seconds=1)
                self.assertFalse(owner.matches(child))
                self.assertEqual([], owner.members())
                self.assertIsNone(foreign.poll())
            finally:
                owner.stop(grace_seconds=1)
                foreign.terminate()
                foreign.wait(timeout=5)

    def test_forceful_cleanup_handles_a_child_ignoring_term(self):
        with tempfile.TemporaryDirectory() as temporary:
            environment = os.environ.copy()
            environment["XDG_CONFIG_HOME"] = temporary
            owner = OwnedProcesses(environment)
            ready = Path(temporary) / "ready"
            process = subprocess.Popen([
                sys.executable, "-c",
                "import signal,time,pathlib,sys; signal.signal(signal.SIGTERM,signal.SIG_IGN); "
                "pathlib.Path(sys.argv[1]).touch(); time.sleep(60)", str(ready)],
                env=environment, start_new_session=True)
            try:
                deadline = time.monotonic() + 5
                while not ready.exists() and time.monotonic() < deadline:
                    time.sleep(0.02)
                self.assertTrue(ready.exists())
                owner.stop(grace_seconds=0.2)
                self.assertEqual(-signal.SIGKILL, process.wait(timeout=5))
            finally:
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=5)


if __name__ == "__main__":
    unittest.main()
