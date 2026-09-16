#!/usr/bin/env python3
"""Exercise the production iOS headroom policy without claiming native execution."""
import subprocess
import tempfile
from pathlib import Path
ios = Path(__file__).resolve().parents[2]
with tempfile.TemporaryDirectory(prefix="overte-ios-pressure-") as scratch:
    binary = str(Path(scratch) / "test")
    subprocess.run(["c++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
                    str(ios / "performance/NativeMetrics.cpp"),
                    str(Path(__file__).with_suffix(".cpp")), "-o", binary], check=True, timeout=60)
    subprocess.run([binary], check=True, timeout=10)
print("PASS memory pressure thresholds, hysteresis, warning escalation and unavailable native samples")
