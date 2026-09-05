#!/usr/bin/env python3
"""Run the actual iOS PX-15 adapter with test-only native failure injection."""
import subprocess
import tempfile
from pathlib import Path
ios = Path(__file__).resolve().parents[2]
with tempfile.TemporaryDirectory(prefix="overte-ios-px15-") as scratch:
    binary = str(Path(scratch) / "test")
    subprocess.run(["c++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-pthread",
                    str(ios / "src/SecureAccountStore.cpp"), str(ios / "auth/KeychainAccountAdapter.cpp"),
                    str(Path(__file__).with_suffix(".cpp")), "-o", binary], check=True, timeout=60)
    subprocess.run([binary], check=True, timeout=10)
print("PASS actual iOS PX-15 adapter statuses, migration, quarantine and logout; native OS checks pending")
