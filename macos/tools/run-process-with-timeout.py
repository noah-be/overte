#!/usr/bin/env python3
"""Run a process with streamed logging and a bounded TERM/KILL shutdown."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout", type=float, required=True)
    parser.add_argument("--grace", type=float, required=True)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command or args.timeout <= 0 or args.grace < 0:
        parser.error("a command, positive timeout, and non-negative grace are required")

    args.log.parent.mkdir(parents=True, exist_ok=True)
    args.result.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    timed_out = False
    sent_term = False
    sent_kill = False
    return_code: int | None = None

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
            }
            args.result.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    if timed_out:
        return 124
    if return_code is None:
        return 1
    return return_code if return_code >= 0 else 128 - return_code


if __name__ == "__main__":
    raise SystemExit(main())
