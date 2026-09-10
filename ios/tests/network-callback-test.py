#!/usr/bin/env python3
"""Execute cancellation/lifetime checks for the token used by native network callers."""
import subprocess
import tempfile
from pathlib import Path
with tempfile.TemporaryDirectory(prefix="overte-ios-callback-") as scratch:
    binary = str(Path(scratch) / "test")
    subprocess.run(["c++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-pthread",
                    str(Path(__file__).with_suffix(".cpp")), "-o", binary], check=True, timeout=60)
    subprocess.run([binary], check=True, timeout=10)
print("PASS cancellation, replacement, destruction and cross-queue stale callbacks")
