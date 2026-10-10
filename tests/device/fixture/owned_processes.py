"""Reap Linux fixture descendants even when they leave their parent's session."""
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import os
from pathlib import Path
import secrets
import signal
import sys
import time


OWNER_VARIABLE = "OVERTE_E2E_FIXTURE_PROCESS_OWNER"


class OwnedProcesses:
    def __init__(self, environment: dict[str, str]):
        self.owner = secrets.token_hex(32)
        self.config_home = environment["XDG_CONFIG_HOME"]
        environment[OWNER_VARIABLE] = self.owner

    def matches(self, pid: int) -> bool:
        root = Path("/proc") / str(pid)
        try:
            if root.stat().st_uid != os.getuid():
                return False
            # Zombies have no remaining runtime or usable environment.
            fields = (root / "stat").read_text().rsplit(")", 1)[1].split()
            if fields[0] == "Z":
                return False
            environment = (root / "environ").read_bytes().split(b"\0")
            return (f"{OWNER_VARIABLE}={self.owner}".encode() in environment
                    and f"XDG_CONFIG_HOME={self.config_home}".encode() in environment)
        except (OSError, IndexError):
            return False

    def members(self) -> list[int]:
        return [int(root.name) for root in Path("/proc").iterdir()
                if root.name.isdecimal() and self.matches(int(root.name))]

    def send_signal(self, pid: int, number: int) -> None:
        # Pin the actual process before rechecking ownership. A reused PID can
        # never turn a delayed cleanup into a signal for an unrelated process.
        try:
            descriptor = os.pidfd_open(pid)
        except ProcessLookupError:
            return
        try:
            if self.matches(pid):
                try:
                    signal.pidfd_send_signal(descriptor, number)
                except ProcessLookupError:
                    pass
        finally:
            os.close(descriptor)

    def stop(self, grace_seconds: float = 5) -> None:
        if not sys.platform.startswith("linux"):
            return  # Other hosts retain the controller's process-group cleanup.
        for number in (signal.SIGTERM, signal.SIGKILL):
            deadline = time.monotonic() + grace_seconds
            signalled = set()
            while True:
                members = self.members()
                if not members:
                    return
                for pid in members:
                    if pid not in signalled:
                        self.send_signal(pid, number)
                        signalled.add(pid)
                if time.monotonic() >= deadline:
                    break
                time.sleep(0.05)
        if self.members():
            raise RuntimeError("owned domain fixture descendants survived cleanup")
