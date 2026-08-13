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
    success_metadata = json.loads(success_result.read_text())
    assert success_metadata["timed_out"] is False
    assert success_metadata["executable"] == Path(sys.executable).name
    assert success_metadata["argument_count"] == 2
    assert "command" not in success_metadata
    assert success_result.stat().st_mode & 0o777 == 0o600

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
        # Leave enough startup time for a cold Python 3.14 interpreter on a
        # loaded hosted macOS runner.  The child still spends essentially the
        # entire interval idle, so this remains an inactivity/TERM/KILL test
        # rather than a scheduler-speed test.
        [sys.executable, str(SUPERVISOR), "--timeout", "1", "--grace", "0.1",
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
    assert timeout_metadata["sample_name"] == timeout_sample.name
    assert str(timeout_sample) not in timeout_result.read_text(encoding="utf-8")
    assert timeout_sample.read_text(encoding="utf-8") == "sampled blocked process\n"

    hanging_tools = output / "hanging-tools"
    hanging_tools.mkdir()
    hanging_sample = hanging_tools / "sample"
    hanging_sample.write_text("#!/bin/sh\nsleep 30\n", encoding="utf-8")
    hanging_sample.chmod(0o755)
    hanging_result = output / "hanging-sample.json"
    hanging = subprocess.run(
        [sys.executable, str(SUPERVISOR), "--timeout", "0.1", "--grace", "0.1",
         "--log", str(output / "hanging-sample.log"), "--result", str(hanging_result),
         "--sample", str(output / "unused.sample"), "--",
         sys.executable, "-c", child],
        check=False,
        timeout=20,
        env={**os.environ, "PATH": f"{hanging_tools}:{os.environ.get('PATH', '')}"},
    )
    assert hanging.returncode == 124
    hanging_metadata = json.loads(hanging_result.read_text())
    assert hanging_metadata["sample_timed_out"] is True
    assert hanging_metadata["sent_sigterm"] is True
    assert hanging_metadata["sent_sigkill"] is True

    crash_reports = output / "diagnostic-reports"
    crash_reports.mkdir()
    executable_name = Path(sys.executable).name
    native_report = crash_reports / f"{executable_name}-test.ips"
    native_report.write_text("native crash evidence\n", encoding="utf-8")
    copied_report = output / "captured.crash.ips"
    crash_result = output / "crash.json"
    crashed = subprocess.run(
        [sys.executable, str(SUPERVISOR), "--timeout", "2", "--grace", "0.1",
         "--log", str(output / "crash.log"), "--result", str(crash_result),
         "--crash-report", str(copied_report),
         "--crash-report-dir", str(crash_reports), "--crash-report-wait", "0", "--",
         sys.executable, "-c", "import os, signal; os.kill(os.getpid(), signal.SIGSEGV)"],
        check=False,
        timeout=5,
    )
    assert crashed.returncode == 139
    assert copied_report.read_text(encoding="utf-8") == "native crash evidence\n"
    crash_metadata = json.loads(crash_result.read_text())
    assert crash_metadata["crash_report_succeeded"] is True
    assert crash_metadata["crash_report_source_name"] == native_report.name
    assert str(crash_reports) not in crash_result.read_text(encoding="utf-8")

print("macOS smoke timeout contract valid")
