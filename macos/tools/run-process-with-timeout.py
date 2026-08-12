#!/usr/bin/env python3
"""Run a process with streamed logging and a bounded TERM/KILL shutdown."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import signal
import shutil
import subprocess
import sys
import time


def capture_macos_crash_report(
    command: list[str],
    destination: Path,
    report_directory: Path,
    started_wall_time: float,
    wait_seconds: float,
) -> tuple[bool, str | None]:
    """Copy the newest matching macOS crash report after a signalled exit."""
    executable_name = Path(command[0]).name
    deadline = time.monotonic() + wait_seconds
    while True:
        candidates = []
        if report_directory.is_dir():
            for suffix in ("ips", "crash"):
                candidates.extend(report_directory.glob(f"{executable_name}*.{suffix}"))
        candidates = [
            candidate
            for candidate in candidates
            if candidate.is_file() and candidate.stat().st_mtime >= started_wall_time - 2
        ]
        if candidates:
            source = max(candidates, key=lambda candidate: candidate.stat().st_mtime)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            return True, str(source)
        if time.monotonic() >= deadline:
            return False, None
        time.sleep(0.25)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout", type=float, required=True)
    parser.add_argument("--grace", type=float, required=True)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--sample", type=Path)
    parser.add_argument("--crash-report", type=Path)
    parser.add_argument("--crash-report-dir", type=Path)
    parser.add_argument("--crash-report-wait", type=float, default=10.0)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command or args.timeout <= 0 or args.grace < 0 or args.crash_report_wait < 0:
        parser.error("a command, positive timeout, and non-negative grace/report wait are required")

    args.log.parent.mkdir(parents=True, exist_ok=True)
    args.result.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    timed_out = False
    sent_term = False
    sent_kill = False
    return_code: int | None = None
    sample_succeeded = False
    sample_timed_out = False
    crash_report_succeeded = False
    crash_report_source: str | None = None
    started_wall_time = time.time()

    with args.log.open("w", encoding="utf-8", errors="replace") as log_stream:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            errors="replace",
            start_new_session=True,
        )
        assert process.stdout is not None
        try:
            # A reader thread prevents a verbose application from filling its
            # pipe while the main thread enforces the deadline.
            import threading

            def copy_output() -> None:
                for line in process.stdout:
                    sys.stdout.write(line)
                    sys.stdout.flush()
                    log_stream.write(line)
                    log_stream.flush()

            reader = threading.Thread(target=copy_output, daemon=True)
            reader.start()
            try:
                return_code = process.wait(timeout=args.timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                if args.sample:
                    args.sample.parent.mkdir(parents=True, exist_ok=True)
                    sample_tool = shutil.which("sample")
                    if sample_tool:
                        print(
                            f"process exceeded {args.timeout:g}s; capturing thread sample",
                            file=sys.stderr,
                            flush=True,
                        )
                        try:
                            sampled = subprocess.run(
                                [sample_tool, str(process.pid), "5", "5", "-file", str(args.sample)],
                                check=False,
                                timeout=15,
                            )
                            sample_succeeded = sampled.returncode == 0 and args.sample.is_file()
                        except subprocess.TimeoutExpired:
                            sample_timed_out = True
                            print(
                                "thread sample exceeded 15s; continuing process cleanup",
                                file=sys.stderr,
                                flush=True,
                            )
                    else:
                        print("sample tool is unavailable; skipping thread sample", file=sys.stderr, flush=True)
                sent_term = True
                print(
                    f"process exceeded {args.timeout:g}s; sending SIGTERM",
                    file=sys.stderr,
                    flush=True,
                )
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    return_code = process.wait(timeout=args.grace)
                except subprocess.TimeoutExpired:
                    sent_kill = True
                    print(
                        f"process ignored SIGTERM for {args.grace:g}s; sending SIGKILL",
                        file=sys.stderr,
                        flush=True,
                    )
                    os.killpg(process.pid, signal.SIGKILL)
                    return_code = process.wait()
            reader.join(timeout=5)
            if return_code is not None and return_code < 0 and args.crash_report:
                report_directory = args.crash_report_dir
                if report_directory is None and sys.platform == "darwin":
                    report_directory = Path.home() / "Library/Logs/DiagnosticReports"
                if report_directory is not None:
                    crash_report_succeeded, crash_report_source = capture_macos_crash_report(
                        command,
                        args.crash_report,
                        report_directory,
                        started_wall_time,
                        args.crash_report_wait,
                    )
        except BaseException:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=args.grace)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
            raise
        finally:
            elapsed = time.monotonic() - started
            result = {
                "command": command,
                "elapsed_seconds": round(elapsed, 3),
                "exit_code": return_code,
                "timed_out": timed_out,
                "sent_sigterm": sent_term,
                "sent_sigkill": sent_kill,
                "sample_path": str(args.sample) if args.sample else None,
                "sample_succeeded": sample_succeeded,
                "sample_timed_out": sample_timed_out,
                "crash_report_path": str(args.crash_report) if args.crash_report else None,
                "crash_report_succeeded": crash_report_succeeded,
                "crash_report_source": crash_report_source,
            }
            args.result.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    if timed_out:
        return 124
    if return_code is None:
        return 1
    return return_code if return_code >= 0 else 128 - return_code


if __name__ == "__main__":
    raise SystemExit(main())
