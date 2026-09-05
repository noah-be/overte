#!/usr/bin/env python3
"""Execute actual preview attempt adapter with the original SH-005 transition engine."""
import subprocess
import tempfile
from pathlib import Path

with tempfile.TemporaryDirectory(prefix="ios-directory-gate-") as scratch:
    binary = str(Path(scratch) / "test")
    subprocess.run(["c++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-pthread",
                    str(Path(__file__).with_suffix(".cpp")), "-o", binary], check=True, timeout=60)
    subprocess.run([binary], check=True, timeout=10)
print("PASS real preview SH-005 adapter: deadlines, retries, stale callbacks, visibility and terminal stop")
