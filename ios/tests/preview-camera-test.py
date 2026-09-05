#!/usr/bin/env python3
"""Run the camera bounds shared by actual native gestures and accessibility actions."""
import subprocess
import tempfile
from pathlib import Path
with tempfile.TemporaryDirectory(prefix="overte-ios-input-") as scratch:
    binary = str(Path(scratch) / "test")
    subprocess.run(["c++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
                    str(Path(__file__).with_suffix(".cpp")), "-o", binary], check=True, timeout=60)
    subprocess.run([binary], check=True, timeout=10)
print("PASS finite bounded camera gestures and accessibility actions")
