#!/usr/bin/env python3
"""Exercise the production iOS watchdog gate and check the real caller wiring."""
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0
import subprocess
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[2]
with tempfile.TemporaryDirectory(prefix="overte-ios-watchdog-") as scratch:
    binary = str(Path(scratch) / "test")
    subprocess.run(["c++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-pthread",
                    str(Path(__file__).with_suffix(".cpp")), "-o", binary],
                   check=True, timeout=60)
    subprocess.run([binary], check=True, timeout=10)

setup = (root / "interface/src/Application_Setup.cpp").read_text()
block = setup.split("if (!DISABLE_WATCHDOG) {", 1)[1].split("// Main thread timer", 1)[0]
assert block.index("&QGuiApplication::applicationStateChanged") < block.index("deadlockWatchdogThread->start()")
assert "Qt::DirectConnection" in block
assert "DeadlockWatchdogThread::setApplicationActive(applicationState() == Qt::ApplicationActive)" in block
header = (root / "interface/src/DeadlockWatchdog.h").read_text()
loop = header.split("void run() override", 1)[1]
assert loop.index("_iosLifecycle.acquireCheck()") < loop.index("uint64_t lastHeartbeat = _heartbeat")
assert "if (!lifecycleCheck.active())" in loop
assert "static inline overte::ios::ForegroundWatchdog _iosLifecycle" in header
print("PASS production iOS watchdog: suspension/resume, foreground timeout, duplicate events, serialized checks; UIKit unexecuted")
