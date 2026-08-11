#!/usr/bin/env python3
"""Run a build while preserving its log and publishing bounded CI progress."""

import argparse
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


def workflow_escape(value: str) -> str:
    return value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def publish(message: str) -> None:
    print(f"macOS build progress: {message}", flush=True)
    if os.environ.get("GITHUB_ACTIONS") == "true":
        print(
            f"::notice title=macOS build progress::{workflow_escape(message)}",
            flush=True,
        )


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
    parser.add_argument("--heartbeat-seconds", type=float, default=60.0)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("a command is required after --")
    if args.heartbeat_seconds <= 0:
        parser.error("--heartbeat-seconds must be positive")

    log_path = Path(args.log)
    result_path = Path(args.result)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.parent.mkdir(parents=True, exist_ok=True)

    started = time.monotonic()
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        start_new_session=True,
    )
    assert process.stdout is not None

    def forward_signal(signum, _frame):
        if process.poll() is None:
            os.killpg(process.pid, signum)

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
    latest_output = ""
    last_publish = 0.0
    publish("phase=build progress=0/100")
    last_publish = time.monotonic()

    with log_path.open("w", encoding="utf-8", buffering=1) as build_log:
        while True:
            timeout = max(0.05, min(1.0, args.heartbeat_seconds / 4))
            try:
                line = output_queue.get(timeout=timeout)
            except queue.Empty:
                line = ""

            if line is None:
                break
            if line:
                sys.stdout.write(line)
                sys.stdout.flush()
                build_log.write(line)
                latest_output = line.strip()
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

            now = time.monotonic()
            if now - last_publish >= args.heartbeat_seconds:
                progress = f"{max(percentage, 0)}/100"
                latest = latest_output[-180:] if latest_output else "waiting for build output"
                publish(f"phase={phase} progress={progress} latest={latest}")
                last_publish = now

    exit_code = process.wait()
    reader.join(timeout=1)
    elapsed = round(time.monotonic() - started, 3)
    metadata = {
        "command": command,
        "elapsed_seconds": elapsed,
        "exit_code": exit_code,
        "max_progress": max(percentage, 0),
        "final_phase": phase,
        "latest_output": latest_output,
    }
    result_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    publish(
        f"phase={'complete' if exit_code == 0 else 'failed'} "
        f"progress={max(percentage, 0)}/100 exit={exit_code} elapsed={elapsed}s"
    )
    return exit_code if exit_code >= 0 else 128 - exit_code


if __name__ == "__main__":
    raise SystemExit(main())
