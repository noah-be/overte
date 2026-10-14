#!/usr/bin/env python3
"""Compile real iOS QtWebChannel transport and execute real shipped JS clients."""
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0
import ctypes.util
import os
from pathlib import Path
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
flags = shlex.split(subprocess.check_output(["pkg-config", "--cflags", "--libs", "Qt6Core"], text=True))
webchannel = subprocess.run(["pkg-config", "--cflags", "--libs", "Qt6WebChannel"], text=True, capture_output=True)
if webchannel.returncode == 0:
    flags += shlex.split(webchannel.stdout)
else:
    include = os.environ.get("OVERTE_TEST_QT_WEBCHANNEL_INCLUDE")
    library = ctypes.util.find_library("Qt6WebChannel")
    if not include or not library:
        raise SystemExit("Qt6WebChannel development files are required (or extracted matching headers via OVERTE_TEST_QT_WEBCHANNEL_INCLUDE).")
    flags += ["-I" + include, "-I" + str(Path(include) / "QtWebChannel"), "-l:" + library]
moc = str(Path(subprocess.check_output(["pkg-config", "--variable=libexecdir", "Qt6Core"], text=True).strip()) / "moc")
flags = [part for flag in flags for part in (["-isystem", flag[2:]] if flag.startswith("-I") else [flag])]
with tempfile.TemporaryDirectory(prefix="ios-web-channel-") as temporary:
    temporary = Path(temporary)
    generated = temporary / "moc_IOSWebChannel.cpp"
    subprocess.run([moc, str(ROOT / "ios/web/IOSWebChannel.h"), "-o", str(generated)], check=True, timeout=30)
    binary = temporary / "test"
    subprocess.run(["c++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-fPIC",
                    str(ROOT / "ios/web/IOSWebChannel.cpp"), str(generated),
                    str(Path(__file__).with_suffix(".cpp")), "-o", str(binary), *flags], check=True, timeout=60)
    subprocess.run([str(binary), str(Path(__file__).with_suffix(".js")),
                    str(ROOT / "interface/resources/html/createGlobalEventBridge.js")], check=True, timeout=15)
