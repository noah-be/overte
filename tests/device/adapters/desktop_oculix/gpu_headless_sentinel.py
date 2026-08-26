#!/usr/bin/env python3
"""Persist Mutter's private Xwayland handoff and remain lifecycle-owned."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import signal
import stat
import tempfile
import time


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--handoff", required=True)
    args = parser.parse_args()
    requested = Path(args.handoff)
    if not requested.is_absolute() or requested.name in {"", ".", ".."}:
        raise RuntimeError("GPU handoff path must be an absolute file path")
    parent = requested.parent.resolve(strict=True)
    destination = parent / requested.name
    details = parent.lstat()
    if (not stat.S_ISDIR(details.st_mode) or details.st_uid != os.getuid()
            or details.st_mode & 0o077):
        raise RuntimeError("GPU handoff directory must be private and user-owned")

    required = {name: os.environ.get(name) for name in (
        "DISPLAY", "XAUTHORITY", "WAYLAND_DISPLAY",
    )}
    if not all(isinstance(value, str) and value and "\x00" not in value
               for value in required.values()):
        raise RuntimeError("Mutter did not provide a complete display handoff")
    payload = {
        "schemaVersion": 1,
        **required,
        "pid": os.getpid(),
        "parentPid": os.getppid(),
        "processGroup": os.getpgrp(),
    }
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".gpu-handoff-", suffix=".tmp", dir=parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8", closefd=True) as output:
            json.dump(payload, output, sort_keys=True, separators=(",", ":"))
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        # Publish without replacing any endpoint created after the lifecycle
        # owner's preflight. A hard link is atomic and fails closed if the
        # destination already exists (including as a symlink).
        os.link(temporary, destination, follow_symlinks=False)
        temporary.unlink()
        directory_descriptor = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    finally:
        try:
            os.close(descriptor)
        except OSError:
            pass
        temporary.unlink(missing_ok=True)

    running = True

    def stop(_signum: int, _frame: object) -> None:
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    while running:
        time.sleep(0.1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
