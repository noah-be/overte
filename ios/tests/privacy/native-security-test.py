#!/usr/bin/env python3
"""Host checks for native bounds and closed diagnostic payloads, not Keychain proof."""
import subprocess
import tempfile
from pathlib import Path

ios = Path(__file__).resolve().parents[2]
with tempfile.TemporaryDirectory(prefix="overte-ios-security-") as scratch:
    binary = str(Path(scratch) / "test")
    subprocess.run(["c++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
                    "-I" + str(ios / "src"), str(ios / "src/SecureAccountStore.cpp"),
                    str(ios / "tests/privacy/native-security-test.cpp"), "-o", binary],
                   check=True, timeout=60)
    subprocess.run([binary], check=True, timeout=10)
print("PASS native storage bounds and fixed diagnostic events; native Keychain execution pending")
