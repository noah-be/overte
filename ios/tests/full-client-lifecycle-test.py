#!/usr/bin/env python3
"""Execute actual iOS Qt startup seeding with original SH-005 Gate and a test owner."""
import os
import shlex
import subprocess
import tempfile
from pathlib import Path

ios = Path(__file__).resolve().parents[1]
flags = shlex.split(subprocess.check_output(
    ["pkg-config", "--cflags", "--libs", "Qt6Gui"], text=True, timeout=10))
flags = [part for flag in flags for part in
         (["-isystem", flag[2:]] if flag.startswith("-I") else [flag])]
with tempfile.TemporaryDirectory(prefix="ios-startup-lifecycle-") as scratch:
    binary = str(Path(scratch) / "test")
    subprocess.run(["c++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-fPIC",
                    str(ios / "lifecycle/FullClientLifecycle.cpp"),
                    str(Path(__file__).with_suffix(".cpp")), "-o", binary, *flags],
                   check=True, timeout=60)
    subprocess.run([binary], check=True, timeout=10,
                   env=dict(os.environ, QT_QPA_PLATFORM="offscreen", XDG_RUNTIME_DIR=scratch))
print("PASS actual iOS Qt initial lifecycle seeding; full Application/native execution pending")
