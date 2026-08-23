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
    assert success_metadata["completion_file_observed"] is False
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

    periodic_log = output / "periodic.log"
    periodic_result = output / "periodic.json"
    periodic_sample = output / "periodic.sample.txt"
    periodically_sampled = subprocess.run(
        [sys.executable, str(SUPERVISOR), "--timeout", "3", "--grace", "0.1",
         "--log", str(periodic_log), "--result", str(periodic_result),
         "--sample", str(periodic_sample), "--periodic-sample-interval", "0.1",
         "--periodic-sample-count", "2", "--",
         sys.executable, "-c", "import time; time.sleep(0.6)"],
        check=False,
        timeout=5,
        env={**os.environ, "PATH": f"{tools}:{os.environ.get('PATH', '')}"},
    )
    assert periodically_sampled.returncode == 0
    periodic_metadata = json.loads(periodic_result.read_text(encoding="utf-8"))
    assert periodic_metadata["timed_out"] is False
    assert periodic_metadata["periodic_sample_attempts"] == 2
    assert periodic_metadata["periodic_samples_succeeded"] == 2
    assert periodic_metadata["periodic_samples_timed_out"] == 0
    assert periodic_metadata["periodic_sample_names"] == [
        "periodic.sample.periodic-01.txt",
        "periodic.sample.periodic-02.txt",
    ]
    for sample_name in periodic_metadata["periodic_sample_names"]:
        assert (output / sample_name).read_text(encoding="utf-8") == (
            "sampled blocked process\n"
        )
    assert str(output) not in periodic_result.read_text(encoding="utf-8")

    completion_file = output / "private-completion-secret.json"
    completion_result = output / "completion.json"
    completion_child = (
        "import pathlib,signal,sys,time; "
        "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        "pathlib.Path(sys.argv[1]).write_text('complete\\n'); "
        "print('completion written', flush=True); time.sleep(30)"
    )
    completed_by_file = subprocess.run(
        [sys.executable, str(SUPERVISOR), "--timeout", "5", "--grace", "0.1",
         "--log", str(output / "completion.log"), "--result", str(completion_result),
         "--completion-file", str(completion_file), "--",
         sys.executable, "-c", completion_child, str(completion_file)],
        check=False,
        timeout=5,
    )
    assert completed_by_file.returncode == 0
    completion_metadata = json.loads(completion_result.read_text(encoding="utf-8"))
    assert completion_metadata["completion_file_observed"] is True
    assert completion_metadata["terminated_after_completion"] is True
    assert completion_metadata["timed_out"] is False
    assert completion_metadata["sent_sigterm"] is True
    assert completion_metadata["sent_sigkill"] is True
    assert str(completion_file) not in completion_result.read_text(encoding="utf-8")

    stale_completion = subprocess.run(
        [sys.executable, str(SUPERVISOR), "--timeout", "1", "--grace", "0.1",
         "--log", str(output / "stale.log"), "--result", str(output / "stale.json"),
         "--completion-file", str(completion_file), "--", sys.executable, "-c", "pass"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert stale_completion.returncode != 0
    assert "must not exist" in stale_completion.stderr

    crash_completion_file = output / "crash-completion.json"
    crash_completion_result = output / "crash-completion-result.json"
    # A Python process that signals itself can be intercepted by hosted-runner
    # crash handlers and linger. Signal the shell directly so this remains a
    # deterministic supervisor exit-code test on both Linux and macOS.
    signal_child = (
        "printf 'complete\\n' > \"$1\"; "
        "kill -SEGV $$"
    )
    crash_after_completion = subprocess.run(
        [sys.executable, str(SUPERVISOR), "--timeout", "5", "--grace", "0.1",
         "--completion-settle", "2",
         "--log", str(output / "crash-completion.log"),
         "--result", str(crash_completion_result),
         "--completion-file", str(crash_completion_file), "--",
         "/bin/sh", "-c", signal_child, "completion-signal-child",
         str(crash_completion_file)],
        check=False,
        timeout=5,
    )
    assert crash_after_completion.returncode == 139
    crash_completion_metadata = json.loads(
        crash_completion_result.read_text(encoding="utf-8")
    )
    assert crash_completion_metadata["completion_file_observed"] is True
    assert crash_completion_metadata["terminated_after_completion"] is False

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
    executable_name = "sh"
    native_report = crash_reports / f"{executable_name}-test.ips"
    native_report.write_text("native crash evidence\n", encoding="utf-8")
    copied_report = output / "captured.crash.ips"
    crash_result = output / "crash.json"
    crashed = subprocess.run(
        [sys.executable, str(SUPERVISOR), "--timeout", "2", "--grace", "0.1",
         "--log", str(output / "crash.log"), "--result", str(crash_result),
         "--crash-report", str(copied_report),
         "--crash-report-dir", str(crash_reports), "--crash-report-wait", "0", "--",
         "/bin/sh", "-c", "kill -SEGV $$"],
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
