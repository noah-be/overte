#!/usr/bin/env python3
"""Execute the original Shared HTTP test with its actual QUuid owner declaration.

General's Apple HTTP fixture replaces the earlier temporary type rewrite.
Full production methods and real Qt abort/timers execute in the original test;
native transport, Qt5 and whole-client acceptance remain pending.
"""
from pathlib import Path
import resource
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
TEST = ROOT / "tests/device/contracts/lifecycle/test_request_cancellation.py"


def main():
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    result = subprocess.run([sys.executable, "-B", str(TEST)], timeout=90, check=False)
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
