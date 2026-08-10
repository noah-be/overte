#!/usr/bin/env python3
"""Bounded subprocess cleanup shared by Android host-test runners."""

from __future__ import annotations

import os
import signal
import subprocess
import time
from typing import Any


def popen_session_kwargs() -> dict[str, Any]:
    """Return portable Popen arguments that isolate a POSIX process group."""
    return {"start_new_session": os.name == "posix"}


def kill_process_group(pid: int, requested_signal: signal.Signals) -> bool:
    """Signal a POSIX process group, tolerating the exit-vs-signal race."""
    try:
        os.killpg(pid, requested_signal)
        return True
    except ProcessLookupError:
        return False


def communicate_with_timeout(
        process: subprocess.Popen, timeout: float, *, termination_grace: float):
    """Communicate or terminate and finally sweep the complete process tree."""
    try:
        return process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as timeout_error:
        termination_started = time.monotonic()
        if os.name == "posix":
            kill_process_group(process.pid, signal.SIGTERM)
        else:
            try:
                process.terminate()
            except ProcessLookupError:
                pass
        try:
            stdout, stderr = process.communicate(timeout=termination_grace)
        except subprocess.TimeoutExpired:
            stdout = stderr = None

        remaining_grace = termination_grace - (time.monotonic() - termination_started)
        if remaining_grace > 0:
            time.sleep(remaining_grace)

        if os.name == "posix":
            # Always sweep the group: the leader or inherited pipes may have
            # exited while a detached descendant remains alive.
            kill_process_group(process.pid, signal.SIGKILL)
        elif process.poll() is None:
            try:
                process.kill()
            except ProcessLookupError:
                pass
        if stdout is None:
            stdout, stderr = process.communicate()
        raise subprocess.TimeoutExpired(
            process.args, timeout_error.timeout, output=stdout, stderr=stderr)
