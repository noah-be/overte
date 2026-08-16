#!/usr/bin/env python3
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

import pathlib
import importlib.util
import os
import signal
import subprocess
import sys
import tempfile
import time
from unittest import mock


REPO = pathlib.Path(__file__).resolve().parents[2]
RUNNER = REPO / "ios/tools/run-with-timeout.py"


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(RUNNER), *args],
        cwd=REPO,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


success = run("5", sys.executable, "-c", "print('ready')")
assert success.returncode == 0, success
assert success.stdout.strip() == "ready", success.stdout

failure = run("5", sys.executable, "-c", "raise SystemExit(17)")
assert failure.returncode == 17, failure

started = time.monotonic()
timed_out = run("0.1", sys.executable, "-c", "import time; time.sleep(30)")
elapsed = time.monotonic() - started
assert timed_out.returncode == 124, timed_out
assert "timed out" in timed_out.stderr, timed_out.stderr
assert elapsed < 3, elapsed

spec = importlib.util.spec_from_file_location("run_with_timeout", RUNNER)
assert spec is not None and spec.loader is not None
runner_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner_module)
fallback_process = subprocess.Popen(
    [sys.executable, "-c", "import time; time.sleep(30)"],
    start_new_session=True,
)
with mock.patch.object(runner_module.os, "killpg", side_effect=PermissionError):
    runner_module.signal_process_tree(fallback_process, signal.SIGTERM)
assert fallback_process.wait(timeout=3) == -signal.SIGTERM

with tempfile.TemporaryDirectory() as directory:
    child_pid_file = pathlib.Path(directory) / "child.pid"
    wrapper = subprocess.Popen(
        [str(RUNNER), "30", sys.executable, "-c",
         "import os,time,pathlib; pathlib.Path(os.environ['CHILD_PID_FILE']).write_text(str(os.getpid())); time.sleep(30)"],
        cwd=REPO,
        env={**os.environ, "CHILD_PID_FILE": str(child_pid_file)},
    )
    for _ in range(100):
        if child_pid_file.exists():
            break
        time.sleep(0.02)
    assert child_pid_file.exists(), "timed command never started"
    child_pid = int(child_pid_file.read_text(encoding="utf-8"))
    wrapper.send_signal(signal.SIGTERM)
    assert wrapper.wait(timeout=3) == 128 + signal.SIGTERM
    try:
        os.kill(child_pid, 0)
    except ProcessLookupError:
        pass
    else:
        raise AssertionError("timed child survived wrapper SIGTERM")

invalid = run("0", "true")
assert invalid.returncode == 2, invalid

print("PASS portable command timeout tests")
