#!/usr/bin/env python3
"""Compile and run the platform-independent iOS lifecycle state machine."""

# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path


IOS_ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    compiler = shutil.which("c++")
    if compiler is None:
        raise RuntimeError("a host C++ compiler is required for lifecycle contracts")
    with tempfile.TemporaryDirectory(prefix="overte-ios-lifecycle-") as temporary:
        executable = Path(temporary) / "lifecycle-state-test"
        command = [
            compiler,
            "-std=c++20",
            "-Wall",
            "-Wextra",
            "-Werror",
            f"-I{IOS_ROOT / 'src'}",
            str(IOS_ROOT / "src/LifecycleStateMachine.cpp"),
            str(IOS_ROOT / "tests/lifecycle-state-test.cpp"),
            "-pthread",
            "-o",
            str(executable),
        ]
        compiled = subprocess.run(command, check=False, capture_output=True, text=True)
        assert compiled.returncode == 0, compiled.stderr
        executed = subprocess.run([str(executable)], check=False, capture_output=True, text=True)
        assert executed.returncode == 0, executed.stderr
    print("PASS iOS lifecycle state-machine tests")


if __name__ == "__main__":
    main()
