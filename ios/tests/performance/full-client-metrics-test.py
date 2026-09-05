#!/usr/bin/env python3
"""Execute real Qt metrics startup/state wiring, with a test-only OS sample."""
import os
import shlex
import subprocess
import tempfile
from pathlib import Path

ios = Path(__file__).resolve().parents[2]
flags = shlex.split(subprocess.check_output(
    ["pkg-config", "--cflags", "--libs", "Qt6Gui"], text=True, timeout=10))
flags = [part for flag in flags for part in
         (["-isystem", flag[2:]] if flag.startswith("-I") else [flag])]
with tempfile.TemporaryDirectory(prefix="overte-ios-metrics-qt-") as scratch:
    binary = str(Path(scratch) / "test")
    subprocess.run(["c++", "-x", "c++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-fPIC",
                    str(ios / "performance/NativeMetrics.cpp"),
                    str(ios / "performance/SharedMetricsPublisher.cpp"),
                    str(ios.parent / "interface/src/metrics/NativeMetrics.cpp"),
                    str(ios / "performance/FullClientMetrics.mm"),
                    str(Path(__file__).with_suffix(".cpp")), "-o", binary, *flags],
                   check=True, timeout=60)
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen", XDG_RUNTIME_DIR=scratch)
    subprocess.run([binary], check=True, timeout=10, env=env)
print("PASS real Qt metrics startup and suspension/resume wiring; native sampling not executed")
