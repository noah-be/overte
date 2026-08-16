#!/usr/bin/env python3
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

"""Run one command with a portable process-group timeout."""

import os
import signal
import subprocess
import sys


def signal_process_tree(process: subprocess.Popen[object], signum: int) -> None:
    """Signal the owned process group, falling back to its direct child."""
    try:
        os.killpg(process.pid, signum)
        return
    except (ProcessLookupError, PermissionError):
        pass
    try:
        process.send_signal(signum)
    except ProcessLookupError:
        pass


def main() -> int:
    if len(sys.argv) < 3:
        print(f"usage: {sys.argv[0]} SECONDS COMMAND [ARG ...]", file=sys.stderr)
        return 2
    try:
        timeout = float(sys.argv[1])
    except ValueError:
        print(f"invalid timeout: {sys.argv[1]}", file=sys.stderr)
        return 2
    if timeout <= 0:
        print("timeout must be positive", file=sys.stderr)
        return 2

    try:
        process = subprocess.Popen(sys.argv[2:], start_new_session=True)
    except FileNotFoundError:
        print(f"command not found: {sys.argv[2]}", file=sys.stderr)
        return 127

    forwarded_signal = None

    def forward_signal(signum: int, _frame: object) -> None:
        nonlocal forwarded_signal
        forwarded_signal = signum
        signal_process_tree(process, signum)

    previous_handlers = {
        signum: signal.signal(signum, forward_signal)
        for signum in (signal.SIGTERM, signal.SIGINT)
    }

    try:
        while True:
            try:
                status = process.wait(timeout=timeout)
                return 128 + forwarded_signal if forwarded_signal is not None else status
            except InterruptedError:
                if forwarded_signal is not None:
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        signal_process_tree(process, signal.SIGKILL)
                        try:
                            process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            pass
                    return 128 + forwarded_signal
    except subprocess.TimeoutExpired:
        print(
            f"command timed out after {timeout:g}s: {' '.join(sys.argv[2:])}",
            file=sys.stderr,
        )
        signal_process_tree(process, signal.SIGTERM)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            signal_process_tree(process, signal.SIGKILL)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                # A kernel- or service-blocked child must not strand the CI
                # wrapper indefinitely or replace the timeout with a traceback.
                pass
        return 124
    finally:
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)


if __name__ == "__main__":
    raise SystemExit(main())
