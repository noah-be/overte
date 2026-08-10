#!/usr/bin/env python3
"""Compile selected iOS preprocessor boundaries without a Qt installation."""

# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path


SOURCE_ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    compiler = shutil.which("c++")
    if compiler is None:
        raise RuntimeError("a host C++ compiler is required for iOS guard contracts")
    request_filters = SOURCE_ROOT / "libraries/ui/src/ui/types/RequestFilters.h"
    with tempfile.TemporaryDirectory(prefix="overte-ios-header-") as temporary:
        root = Path(temporary)
        qt_core = root / "QtCore"
        qt_core.mkdir()
        (qt_core / "QtGlobal").write_text("#pragma once\n", encoding="utf-8")
        translation_unit = root / "guard.cpp"
        translation_unit.write_text(
            f'#include "{request_filters}"\nint main() {{ return 0; }}\n',
            encoding="utf-8",
        )
        result = subprocess.run(
            [
                compiler,
                "-std=c++20",
                "-DQ_OS_IOS=1",
                "-fsyntax-only",
                f"-I{root}",
                str(translation_unit),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
    print("PASS iOS C++ header guard tests")


if __name__ == "__main__":
    main()
