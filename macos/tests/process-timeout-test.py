#!/usr/bin/env python3
"""Hermetic tests for the macOS smoke process supervisor."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import os

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
    timeout_sample = output / "timeout.sample.txt"
    tools = output / "tools"
    tools.mkdir()
    sample_tool = tools / "sample"
    sample_tool.write_text(
        "#!/bin/sh\n"
        "while [ \"$1\" != \"-file\" ]; do shift; done\n"
        "printf 'sampled blocked process\\n' > \"$2\"\n",
        encoding="utf-8",
    )
    sample_tool.chmod(0o755)
    child = (
        "import signal,time; "
        "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        "print('before hang', flush=True); time.sleep(30)"
    )
    timed_out = subprocess.run(
        [sys.executable, str(SUPERVISOR), "--timeout", "0.2", "--grace", "0.1",
         "--log", str(timeout_log), "--result", str(timeout_result),
         "--sample", str(timeout_sample), "--",
         sys.executable, "-c", child],
        check=False,
        timeout=5,
        env={**os.environ, "PATH": f"{tools}:{os.environ.get('PATH', '')}"},
    )
    assert timed_out.returncode == 124
    assert "before hang" in timeout_log.read_text(encoding="utf-8")
    timeout_metadata = json.loads(timeout_result.read_text())
    assert timeout_metadata["timed_out"] is True
    assert timeout_metadata["sent_sigterm"] is True
    assert timeout_metadata["sent_sigkill"] is True
    assert timeout_metadata["sample_succeeded"] is True
    assert timeout_sample.read_text(encoding="utf-8") == "sampled blocked process\n"

print("macOS smoke timeout contract valid")
