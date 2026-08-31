#!/usr/bin/env python3
"""Compile and run the platform-independent pending deep-link store."""

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
        raise RuntimeError("a host C++ compiler is required for deep-link contracts")
    with tempfile.TemporaryDirectory(prefix="overte-ios-deep-link-") as temporary:
        executable = Path(temporary) / "pending-deep-link-test"
        command = [
            compiler,
            "-std=c++20",
            "-Wall",
            "-Wextra",
            "-Werror",
            f"-I{IOS_ROOT / 'src'}",
            str(IOS_ROOT / "src/PendingDeepLinkStore.cpp"),
            str(IOS_ROOT / "tests/pending-deep-link-test.cpp"),
            "-pthread",
            "-o",
            str(executable),
        ]
        compiled = subprocess.run(command, check=False, capture_output=True, text=True)
        assert compiled.returncode == 0, compiled.stderr
        executed = subprocess.run([str(executable)], check=False, capture_output=True, text=True)
        assert executed.returncode == 0, executed.stderr
    print("PASS pending iOS deep-link store tests")


if __name__ == "__main__":
    main()
