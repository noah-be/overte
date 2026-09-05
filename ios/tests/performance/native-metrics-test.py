#!/usr/bin/env python3
"""Exercise truthful unavailable metrics, bounds and native preview degradation."""
import subprocess
import tempfile
from pathlib import Path
ios = Path(__file__).resolve().parents[2]
with tempfile.TemporaryDirectory(prefix="overte-ios-metrics-") as scratch:
    binary = str(Path(scratch) / "test")
    subprocess.run(["c++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
                    str(ios / "performance/NativeMetrics.cpp"),
                    str(Path(__file__).with_suffix(".cpp")), "-o", binary], check=True, timeout=60)
    subprocess.run([binary], check=True, timeout=10)
print("PASS native metrics formatting and preview degradation; native sampling validation pending")
