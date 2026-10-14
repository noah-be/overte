#!/usr/bin/env python3
"""Run iOS native snapshot lifecycle state; does not execute UIKit/WebKit."""
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
import subprocess
import tempfile


with tempfile.TemporaryDirectory(prefix="ios-web-surface-state-") as scratch:
    binary = Path(scratch) / "test"
    subprocess.run(["c++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
                    str(Path(__file__).with_suffix(".cpp")), "-o", str(binary)],
                   check=True, timeout=30)
    subprocess.run([str(binary)], check=True, timeout=10)
print("PASS iOS snapshot lifecycle state; UIKit/WebKit unexecuted")
