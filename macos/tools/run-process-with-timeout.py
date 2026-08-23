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


def capture_thread_sample(
    process_id: int,
    destination: Path,
    description: str,
) -> tuple[bool, bool]:
    """Capture one bounded macOS thread sample without stopping the child."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    sample_tool = shutil.which("sample")
    if not sample_tool:
        print("sample tool is unavailable; skipping thread sample", file=sys.stderr, flush=True)
        return False, False
    print(f"{description}; capturing thread sample", file=sys.stderr, flush=True)
    try:
        sampled = subprocess.run(
            [sample_tool, str(process_id), "5", "5", "-file", str(destination)],
            check=False,
            timeout=15,
        )
        return sampled.returncode == 0 and destination.is_file(), False
    except subprocess.TimeoutExpired:
        print(
            "thread sample exceeded 15s; continuing supervision",
            file=sys.stderr,
            flush=True,
        )
        return False, True


def periodic_sample_path(base: Path, sequence: int) -> Path:
    """Derive a bounded diagnostic name next to the final timeout sample."""
    return base.with_name(f"{base.stem}.periodic-{sequence:02d}{base.suffix}")


def capture_macos_crash_report(
    command: list[str],
    destination: Path,
    report_directories: list[Path],
    started_wall_time: float,
    wait_seconds: float,
) -> tuple[bool, str | None]:
    """Copy the newest matching macOS crash report after a signalled exit."""
    executable_name = Path(command[0]).name
    deadline = time.monotonic() + wait_seconds
    while True:
        candidates = []
        for report_directory in report_directories:
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
    parser.add_argument("--periodic-sample-interval", type=float)
    parser.add_argument("--periodic-sample-count", type=int, default=1)
    parser.add_argument("--crash-report", type=Path)
    parser.add_argument("--crash-report-dir", type=Path)
    parser.add_argument("--crash-report-wait", type=float, default=10.0)
    parser.add_argument("--completion-file", type=Path)
    parser.add_argument("--completion-settle", type=float, default=0.25)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if (not command or args.timeout <= 0 or args.grace < 0 or args.crash_report_wait < 0 or
            args.completion_settle < 0 or args.periodic_sample_count <= 0):
        parser.error("a command, positive timeout, and non-negative grace/report wait are required")
    if args.periodic_sample_interval is not None:
        if args.periodic_sample_interval <= 0 or args.sample is None:
            parser.error("periodic sampling requires --sample and a positive interval")
    if args.completion_file and args.completion_file.exists():
        parser.error("completion file must not exist before the supervised process starts")

    args.log.parent.mkdir(parents=True, exist_ok=True)
    args.result.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    timed_out = False
    sent_term = False
    sent_kill = False
    return_code: int | None = None
    sample_succeeded = False
    sample_timed_out = False
    periodic_sample_attempts = 0
    periodic_samples_succeeded = 0
    periodic_samples_timed_out = 0
    periodic_sample_names: list[str] = []
    crash_report_succeeded = False
    crash_report_source: str | None = None
    completion_file_observed = False
    terminated_after_completion = False
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
            deadline = time.monotonic() + args.timeout
            next_periodic_sample = (
                time.monotonic() + args.periodic_sample_interval
                if args.periodic_sample_interval is not None
                else None
            )
            while return_code is None:
                remaining = deadline - time.monotonic()
                try:
                    return_code = process.wait(timeout=max(0.01, min(0.1, remaining)))
                except subprocess.TimeoutExpired:
                    if (args.completion_file and args.completion_file.is_file() and
                            args.completion_file.stat().st_size > 0):
                        completion_file_observed = True
                        break
                    if (next_periodic_sample is not None and
                            time.monotonic() >= next_periodic_sample and
                            periodic_sample_attempts < args.periodic_sample_count):
                        periodic_sample_attempts += 1
                        periodic_path = periodic_sample_path(
                            args.sample, periodic_sample_attempts
                        )
                        succeeded, sample_timeout = capture_thread_sample(
                            process.pid,
                            periodic_path,
                            f"process remains active after {args.periodic_sample_interval:g}s interval",
                        )
                        periodic_samples_succeeded += int(succeeded)
                        periodic_samples_timed_out += int(sample_timeout)
                        if succeeded:
                            periodic_sample_names.append(periodic_path.name)
                        next_periodic_sample += args.periodic_sample_interval
                        if periodic_sample_attempts >= args.periodic_sample_count:
                            next_periodic_sample = None
                    if time.monotonic() >= deadline:
                        break

            if (args.completion_file and args.completion_file.is_file() and
                    args.completion_file.stat().st_size > 0):
                completion_file_observed = True

            if completion_file_observed and process.poll() is None and args.completion_settle > 0:
                try:
                    return_code = process.wait(timeout=args.completion_settle)
                except subprocess.TimeoutExpired:
                    pass

            if completion_file_observed and process.poll() is None:
                terminated_after_completion = True
                sent_term = True
                print("completion evidence observed; sending SIGTERM", file=sys.stderr, flush=True)
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
            elif return_code is None:
                timed_out = True
                if args.sample:
                    sample_succeeded, sample_timed_out = capture_thread_sample(
                        process.pid,
                        args.sample,
                        f"process exceeded {args.timeout:g}s",
                    )
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
                report_directories = [args.crash_report_dir] if args.crash_report_dir else []
                if not report_directories and sys.platform == "darwin":
                    report_directories = [
                        Path.home() / "Library/Logs/DiagnosticReports",
                        Path.home() / "Library/Logs/CrashReporter",
                        Path("/Library/Logs/DiagnosticReports"),
                    ]
                if report_directories:
                    crash_report_succeeded, crash_report_source = capture_macos_crash_report(
                        command,
                        args.crash_report,
                        report_directories,
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
                # Runtime URLs and script paths may contain private locations.
                # Persist only bounded process identity, never the argv.
                "executable": Path(command[0]).name,
                "argument_count": len(command) - 1,
                "elapsed_seconds": round(elapsed, 3),
                "exit_code": return_code,
                "timed_out": timed_out,
                "completion_file_observed": completion_file_observed,
                "terminated_after_completion": terminated_after_completion,
                "sent_sigterm": sent_term,
                "sent_sigkill": sent_kill,
                "sample_name": args.sample.name if args.sample else None,
                "sample_succeeded": sample_succeeded,
                "sample_timed_out": sample_timed_out,
                "periodic_sample_attempts": periodic_sample_attempts,
                "periodic_samples_succeeded": periodic_samples_succeeded,
                "periodic_samples_timed_out": periodic_samples_timed_out,
                "periodic_sample_names": periodic_sample_names,
                "crash_report_name": args.crash_report.name if args.crash_report else None,
                "crash_report_succeeded": crash_report_succeeded,
                "crash_report_source_name": (
                    Path(crash_report_source).name if crash_report_source else None
                ),
            }
            descriptor = os.open(
                args.result,
                os.O_CREAT | os.O_TRUNC | os.O_WRONLY,
                0o600,
            )
            with os.fdopen(descriptor, "w", encoding="utf-8") as result_stream:
                json.dump(result, result_stream, indent=2)
                result_stream.write("\n")
            os.chmod(args.result, 0o600)

    if terminated_after_completion or (completion_file_observed and return_code == 0):
        return 0
    if timed_out:
        return 124
    if return_code is None:
        return 1
    return return_code if return_code >= 0 else 128 - return_code


if __name__ == "__main__":
    raise SystemExit(main())
