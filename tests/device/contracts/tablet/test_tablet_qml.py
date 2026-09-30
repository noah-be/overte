"""Compile every first-party tablet entry and retained settings editor with Qt 6.

This checks real QML dependencies with explicit native registration stubs. It
does not instantiate complete apps, run native services or claim device coverage.
"""
from pathlib import Path
import os
import shlex
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
flags = shlex.split(subprocess.check_output(
    ["pkg-config", "--cflags", "--libs", "Qt6Gui", "Qt6Qml"], text=True))
with tempfile.TemporaryDirectory(prefix="overte-tablet-qml-") as scratch:
    binary = Path(scratch) / "compile-pages"
    subprocess.run(["c++", "-std=c++17", str(HERE / "compile-pages.cpp"),
                    "-o", str(binary), *flags], check=True, timeout=90)
    modes = ["default"]
    if (ROOT / "interface/resources/qml/controlsUit/+ios/TouchUiProfile.qml").exists():
        modes.append("ios")
    for mode in modes:
        print(f"QML compile profile: {mode}", flush=True)
        subprocess.run([str(binary), str(ROOT), mode], check=True, timeout=60,
                       env={**os.environ, "QT_QPA_PLATFORM": "offscreen"})
