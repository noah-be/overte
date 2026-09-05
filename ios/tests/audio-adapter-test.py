#!/usr/bin/env python3
"""Execute real iOS adapter/gate with native operations replaced by fault fixtures."""
import subprocess
import tempfile
from pathlib import Path
ios = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix="overte-ios-audio-") as scratch:
    binary = str(Path(scratch) / "test")
    subprocess.run(["c++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-pthread",
                    str(ios / "audio/IOSAudioAdapter.cpp"), str(Path(__file__).with_suffix(".cpp")),
                    "-o", binary], check=True, timeout=60)
    subprocess.run([binary], check=True, timeout=10)
print("PASS real iOS audio adapter: permission, stale callbacks, mute, suspension, interruption and stop failure")
