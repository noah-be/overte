#!/usr/bin/env python3
"""Hermetic tests for macOS build progress and checkpoint metadata."""

import json
import os
from pathlib import Path
import subprocess
import signal
import sys
import tempfile
import time


ROOT = Path(__file__).resolve().parents[2]
MONITOR = ROOT / "macos/tools/run-build-with-progress.py"

with tempfile.TemporaryDirectory() as temporary:
    output = Path(temporary)
    child = (
        "import os,time; "
        "assert os.environ['OVERTE_COMPILER_WATCHDOG_DIAGNOSTICS'].endswith('compiler-stalls'); "
        "print('[  5%] Building CXX object', flush=True); "
        "time.sleep(0.08); "
        "print('[ 99%] Linking CXX executable Overte', flush=True); "
        "time.sleep(0.08); "
        "print('Running macdeployqt and deploy-conan-dylibs', flush=True); "
        "print('[100%] Built target Overte', flush=True)"
    )
    completed = subprocess.run(
        [
            sys.executable,
            str(MONITOR),
            "--heartbeat-seconds",
            "0.05",
            "--log",
            str(output / "build.log"),
            "--result",
            str(output / "build.json"),
            "--live-log",
            str(output / "live.jsonl"),
            "--compiler-diagnostics-dir",
            str(output / "compiler-stalls"),
            "--",
            sys.executable,
            "-c",
            child,
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=5,
        env={**os.environ, "GITHUB_ACTIONS": "true"},
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    for phase in ("compile", "link", "bundle", "complete"):
        assert f"phase={phase}" in completed.stdout
    assert "::notice title=macOS build progress::" in completed.stdout
    metadata = json.loads((output / "build.json").read_text(encoding="utf-8"))
    assert metadata["exit_code"] == 0
    assert metadata["max_progress"] == 100
    assert metadata["final_phase"] == "bundle"
    assert "Built target Overte" in (output / "build.log").read_text(encoding="utf-8")
    live_records = [json.loads(line) for line in (output / "live.jsonl").read_text().splitlines()]
    assert live_records[0]["macos_build_supervisor"] == "start"
    assert any(row["macos_build_supervisor"] == "heartbeat" for row in live_records)
    assert live_records[-1]["macos_build_supervisor"] == "end"
    live_text = (output / "live.jsonl").read_text()
    assert "-c" not in live_text and "Building CXX object" not in live_text
    assert (output / "live.jsonl").stat().st_mode & 0o777 == 0o600
    assert (output / "compiler-stalls").stat().st_mode & 0o777 == 0o700

    failed = subprocess.run(
        [
            sys.executable,
            str(MONITOR),
            "--log",
            str(output / "failed.log"),
            "--result",
            str(output / "failed.json"),
            "--live-log",
            str(output / "failed-live.jsonl"),
            "--compiler-diagnostics-dir",
            str(output / "failed-compiler-stalls"),
            "--",
            sys.executable,
            "-c",
            "print('[ 30%] Building CXX object', flush=True); raise SystemExit(7)",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert failed.returncode == 7
    assert "phase=failed" in failed.stdout
    assert json.loads((output / "failed.json").read_text(encoding="utf-8"))["exit_code"] == 7

    signal_result = output / "signal.json"
    signal_live = output / "signal-live.jsonl"
    signal_log = output / "signal.log"
    pid_file = output / "descendant.pid"
    ready_file = output / "descendant.ready"
    descendant_code = (
        "import os,signal,time,pathlib; "
        "signal.signal(signal.SIGTERM,signal.SIG_IGN); "
        f"pathlib.Path({str(ready_file)!r}).write_text(str(os.getpid())); "
        "time.sleep(30)"
    )
    parent_code = (
        "import subprocess,time,pathlib; "
        f"p=subprocess.Popen([{sys.executable!r},'-c',{descendant_code!r}]); "
        f"ready=pathlib.Path({str(ready_file)!r}); "
        "end=time.time()+2; "
        "exec('while not ready.exists() and time.time()<end: time.sleep(.01)'); "
        f"pathlib.Path({str(pid_file)!r}).write_text(str(p.pid)); time.sleep(30)"
    )
    process = subprocess.Popen(
        [
            sys.executable, str(MONITOR), "--heartbeat-seconds", "0.05",
            "--term-grace-seconds", "0.1", "--log", str(signal_log),
            "--result", str(signal_result), "--live-log", str(signal_live),
            "--compiler-diagnostics-dir", str(output / "signal-compiler-stalls"),
            "--",
            sys.executable, "-c",
            parent_code,
        ],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    deadline = time.monotonic() + 2
    while not pid_file.exists() and time.monotonic() < deadline:
        time.sleep(0.02)
    assert pid_file.exists()
    assert process.poll() is None
    assert '"macos_build_supervisor":"start"' in signal_live.read_text()
    descendant = int(pid_file.read_text())
    process.send_signal(signal.SIGTERM)
    assert process.wait(timeout=3) == 143
    assert json.loads(signal_result.read_text())["exit_code"] == 143
    deadline = time.monotonic() + 1
    while time.monotonic() < deadline:
        state = subprocess.run(
            ["ps", "-o", "stat=", "-p", str(descendant)], capture_output=True, text=True
        ).stdout.strip()
        if not state or state.startswith("Z"):
            break
        time.sleep(0.02)
    else:
        raise AssertionError("descendant survived process-group termination")

    secret = "/secret/private/compiler-argument.cpp"
    secret_value = "private-signing-value"
    redacted = subprocess.run(
        [sys.executable, str(MONITOR), "--log", str(output / "redacted.log"),
         "--result", str(output / "redacted.json"), "--live-log",
         str(output / "redacted-live.jsonl"), "--compiler-diagnostics-dir",
         str(output / "redacted-compiler-stalls"), "--", sys.executable, "-c",
         "import os; print('/usr/bin/clang -c /secret/private/unit.cpp -o /secret/private/unit.o'); "
         "print('SIGNING_TOKEN=' + os.environ['SIGNING_TOKEN']); raise SystemExit(0)", secret],
        capture_output=True, text=True, check=False, timeout=5,
        env={**os.environ, "SIGNING_TOKEN": secret_value},
    )
    assert redacted.returncode == 0
    all_diagnostics = redacted.stdout + (output / "redacted.log").read_text() + \
        (output / "redacted-live.jsonl").read_text() + (output / "redacted.json").read_text()
    assert secret not in all_diagnostics
    assert secret_value not in all_diagnostics
    assert "/secret/private" not in all_diagnostics
    assert "clang -c" not in all_diagnostics

print("macOS build progress contract valid")
