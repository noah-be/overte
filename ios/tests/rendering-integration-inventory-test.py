#!/usr/bin/env python3
"""Host entry point for the native iOS rendering graph audit."""

import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
raise SystemExit(subprocess.run(
    [sys.executable, str(ROOT / "ios/tools/validate-rendering-integration.py")],
    cwd=ROOT,
).returncode)
