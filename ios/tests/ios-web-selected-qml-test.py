#!/usr/bin/env python3
"""Compile production selected iOS QML and Chat, substituting native SDK only."""
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0
import os
from pathlib import Path
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
flags = shlex.split(subprocess.check_output(["pkg-config", "--cflags", "--libs", "Qt6Gui", "Qt6Qml"], text=True))
with tempfile.TemporaryDirectory(prefix="ios-selected-web-qml-") as temporary:
    binary = Path(temporary) / "test"
    subprocess.run(["c++", "-std=c++17", "-fPIC", "-I" + str(ROOT / "libraries/ui/src"),
                    str(Path(__file__).with_suffix(".cpp")), "-o", str(binary), *flags], check=True, timeout=90)
    subprocess.run([str(binary), str(ROOT)], check=True, timeout=60,
                   env=os.environ | {"QT_QPA_PLATFORM": "offscreen"})
