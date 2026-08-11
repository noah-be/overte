#!/usr/bin/env python3
"""Hermetic tests for the macOS smoke process supervisor."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
SUPERVISOR = ROOT / "macos/tools/run-process-with-timeout.py"

with tempfile.TemporaryDirectory() as temporary:
    output = Path(temporary)
    success_log = output / "success.log"
    success_result = output / "success.json"
    completed = subprocess.run(
        [sys.executable, str(SUPERVISOR), "--timeout", "2", "--grace", "0.1",
         "--log", str(success_log), "--result", str(success_result), "--",
         sys.executable, "-c", "print('runtime evidence')"],
        check=False,
    )
    assert completed.returncode == 0
    assert "runtime evidence" in success_log.read_text(encoding="utf-8")
    assert json.loads(success_result.read_text())["timed_out"] is False

    timeout_log = output / "timeout.log"
    timeout_result = output / "timeout.json"
    child = (
        "import signal,time; "
        "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        "print('before hang', flush=True); time.sleep(30)"
    )
    timed_out = subprocess.run(
        [sys.executable, str(SUPERVISOR), "--timeout", "0.2", "--grace", "0.1",
         "--log", str(timeout_log), "--result", str(timeout_result), "--",
         sys.executable, "-c", child],
        check=False,
        timeout=5,
    )
    assert timed_out.returncode == 124
    assert "before hang" in timeout_log.read_text(encoding="utf-8")
    timeout_metadata = json.loads(timeout_result.read_text())
    assert timeout_metadata["timed_out"] is True
    assert timeout_metadata["sent_sigterm"] is True
    assert timeout_metadata["sent_sigkill"] is True

print("macOS smoke timeout contract valid")
