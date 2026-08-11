#!/usr/bin/env python3
"""Run a build while preserving its log and publishing bounded CI progress."""

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import queue
import re
import signal
import subprocess
import sys
import threading
import time


PROGRESS = re.compile(r"\[\s*(\d+)%\]")
BUNDLE_MARKERS = (
    "macdeployqt",
    "deploy-conan-dylibs",
    "deploying conan",
    "fixing up",
)
LINK_MARKERS = ("linking cxx", "linking c ", "linking objective-c")
COMPILER_COMMAND = re.compile(
    r"(?:^|\s)(?:/\S*/)?(?:clang(?:\+\+)?|gcc|g\+\+|cc|c\+\+)\s+.*(?:\s-c\s|\s-o\s)"
)
SECRET_ASSIGNMENT = re.compile(
    r"(?i)((?:token|secret|password|passwd|credential|signing|api[_-]?key)\s*[:=]\s*)(?:\S+)"
)
ABSOLUTE_PATH = re.compile(r"(?<![A-Za-z0-9_.-])/(?:[^\s\"'<>|:]+/?)+")


def workflow_escape(value: str) -> str:
    return value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def publish(message: str) -> None:
    print(f"macOS build progress: {message}", flush=True)
    if os.environ.get("GITHUB_ACTIONS") == "true":
        print(
            f"::notice title=macOS build progress::{workflow_escape(message)}",
            flush=True,
        )


def sanitize_build_line(line: str) -> str:
    """Keep diagnostics useful without retaining commands, secrets, or full paths."""
    if COMPILER_COMMAND.search(line):
        return "[compiler invocation redacted; see structured watchdog records]\n"
    for name, value in os.environ.items():
        if value and len(value) >= 4 and re.search(
            r"(?i)(?:token|secret|password|passwd|credential|signing|api[_-]?key)", name
        ):
            line = line.replace(value, "<redacted-secret>")
    line = SECRET_ASSIGNMENT.sub(r"\1<redacted-secret>", line)

    def redact_path(match: re.Match[str]) -> str:
        value = match.group(0).rstrip("/")
        basename = Path(value).name
        return f"<redacted-path>/{basename}" if basename else "<redacted-path>"

    return ABSOLUTE_PATH.sub(redact_path, line)


def append_live_record(path: Path, event: str, started: float, **fields: object) -> None:
    """Append one deliberately argument- and environment-free status record."""
    record = {
        "macos_build_supervisor": event,
        "utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "elapsed_s": round(time.monotonic() - started, 1),
    }
    record.update(fields)
    descriptor = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
    try:
        os.write(descriptor, (json.dumps(record, separators=(",", ":"), sort_keys=True) + "\n").encode())
    finally:
        os.close(descriptor)


def stop_process(process: subprocess.Popen, grace: float = 2.0) -> None:
    if process.poll() is not None:
        return
    try:
        process.terminate()
        process.wait(timeout=grace)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def classify_phase(line: str, percentage: int, current: str) -> str:
    lower = line.lower()
    if any(marker in lower for marker in BUNDLE_MARKERS):
        return "bundle"
    if current == "bundle":
        return current
    if any(marker in lower for marker in LINK_MARKERS) or percentage >= 99:
        return "link"
    if percentage >= 0:
        return "compile"
    return current


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", required=True)
    parser.add_argument("--result", required=True)
    parser.add_argument("--live-log", required=True)
    parser.add_argument("--compiler-diagnostics-dir", required=True)
    parser.add_argument("--heartbeat-seconds", type=float, default=30.0)
    parser.add_argument("--term-grace-seconds", type=float, default=10.0)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("a command is required after --")
    if args.heartbeat_seconds <= 0 or args.term_grace_seconds < 0:
        parser.error("heartbeat must be positive and termination grace non-negative")

    log_path = Path(args.log)
    result_path = Path(args.result)
    live_path = Path(args.live_log)
    compiler_diagnostics_dir = Path(args.compiler_diagnostics_dir)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.parent.mkdir(parents=True, exist_ok=True)
    live_path.parent.mkdir(parents=True, exist_ok=True)
    compiler_diagnostics_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    compiler_diagnostics_dir.chmod(0o700)
    descriptor = os.open(live_path, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
    os.close(descriptor)
    live_path.chmod(0o600)

    started = time.monotonic()
    tail = subprocess.Popen(["tail", "-n", "0", "-F", str(live_path)])
    child_env = os.environ.copy()
    child_env["OVERTE_COMPILER_WATCHDOG_LOG"] = str(live_path)
    child_env["OVERTE_COMPILER_WATCHDOG_DIAGNOSTICS"] = str(compiler_diagnostics_dir)
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        start_new_session=True,
        env=child_env,
    )
    assert process.stdout is not None

    forwarded_signal = 0
    termination_deadline = 0.0

    def forward_signal(signum, _frame):
        nonlocal forwarded_signal, termination_deadline
        if not forwarded_signal:
            forwarded_signal = signum
            termination_deadline = time.monotonic() + args.term_grace_seconds
        if process.poll() is None:
            try:
                os.killpg(process.pid, signum)
            except ProcessLookupError:
                pass

    signal.signal(signal.SIGTERM, forward_signal)
    signal.signal(signal.SIGINT, forward_signal)

    output_queue = queue.Queue()

    def read_output():
        for output_line in process.stdout:
            output_queue.put(output_line)
        output_queue.put(None)

    reader = threading.Thread(target=read_output, name="build-output", daemon=True)
    reader.start()

    percentage = -1
    announced_percentage = -5
    phase = "build"
    announced_phase = ""
    last_publish = 0.0
    last_activity = started
    publish("phase=build progress=0/100")
    append_live_record(live_path, "start", started, phase="build", progress=0)
    last_publish = time.monotonic()

    with log_path.open("w", encoding="utf-8", buffering=1) as build_log:
        while True:
            timeout = max(0.05, min(1.0, args.heartbeat_seconds / 4))
            try:
                line = output_queue.get(timeout=timeout)
            except queue.Empty:
                line = ""

            if forwarded_signal and time.monotonic() >= termination_deadline:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                termination_deadline = float("inf")

            if line is None:
                break
            if line:
                safe_line = sanitize_build_line(line)
                sys.stdout.write(safe_line)
                sys.stdout.flush()
                build_log.write(safe_line)
                last_activity = time.monotonic()
                match = PROGRESS.search(line)
                if match:
                    percentage = max(percentage, int(match.group(1)))
                phase = classify_phase(line, percentage, phase)
                if phase != announced_phase or percentage >= announced_percentage + 5:
                    progress = f"{max(percentage, 0)}/100"
                    publish(f"phase={phase} progress={progress}")
                    announced_phase = phase
                    announced_percentage = percentage
                    last_publish = time.monotonic()
                    append_live_record(
                        live_path, "progress", started, phase=phase,
                        progress=max(percentage, 0), inactive_s=0.0,
                    )

            now = time.monotonic()
            if now - last_publish >= args.heartbeat_seconds:
                progress = f"{max(percentage, 0)}/100"
                inactive = round(now - last_activity, 1)
                publish(f"phase={phase} progress={progress} inactive={inactive}s")
                append_live_record(
                    live_path, "heartbeat", started, phase=phase,
                    progress=max(percentage, 0), inactive_s=inactive,
                )
                last_publish = now

    exit_code = process.wait()
    if forwarded_signal:
        reported_exit_code = 128 + forwarded_signal
    elif exit_code < 0:
        reported_exit_code = 128 - exit_code
    else:
        reported_exit_code = exit_code
    reader.join(timeout=1)
    elapsed = round(time.monotonic() - started, 3)
    metadata = {
        "elapsed_seconds": elapsed,
        "exit_code": reported_exit_code,
        "max_progress": max(percentage, 0),
        "final_phase": phase,
    }
    result_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    publish(
        f"phase={'complete' if reported_exit_code == 0 else 'failed'} "
        f"progress={max(percentage, 0)}/100 exit={reported_exit_code} elapsed={elapsed}s"
    )
    append_live_record(
        live_path, "end", started,
        phase="complete" if reported_exit_code == 0 else "failed",
        progress=max(percentage, 0), exit_code=reported_exit_code,
    )
    time.sleep(0.1)
    stop_process(tail)
    return reported_exit_code


if __name__ == "__main__":
    raise SystemExit(main())
