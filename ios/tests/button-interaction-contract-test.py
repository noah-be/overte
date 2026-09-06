#!/usr/bin/env python3
"""Run original Shared control tests with its published Apple source variant.

No local fixture rewrite: General's Apple preferences contract now independently
asserts the retained iOS callback and original nine control/OS input cases.
Host Qt Quick only; this does not execute UIKit or prove native acceptance.
"""
import os
from pathlib import Path
import resource
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
TEST = ROOT / "tests/device/contracts/test_ui_button.py"


def main():
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    result = subprocess.run(
        [sys.executable, "-B", str(TEST)],
        env={**os.environ, "OVERTE_UI_VARIANT": "apple"},
        timeout=90,
        check=False,
    )
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
