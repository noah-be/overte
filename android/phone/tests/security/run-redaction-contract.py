#!/usr/bin/env python3
"""Run unchanged PX-16 v001 C++/Java conformance in isolated host scratch."""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[4]
with tempfile.TemporaryDirectory(prefix="phone-redaction-contract-") as temporary:
    scratch = Path(temporary)
    subprocess.run(["c++", "-std=c++14", "-Wall", "-Wextra", "-Werror",
                    str(ROOT / "tests/device/contracts/redaction/sanitizer-test.cpp"),
                    "-o", str(scratch / "sanitizer")], check=True, timeout=60)
    subprocess.run([str(scratch / "sanitizer")], check=True, timeout=60)
    subprocess.run(["javac", "-proc:none", "-d", str(scratch),
                    str(ROOT / "security/redaction/java/org/overte/security/SafeDiagnostics.java"),
                    str(ROOT / "tests/device/contracts/redaction/SanitizerTest.java")],
                   check=True, timeout=60)
    subprocess.run(["java", "-cp", str(scratch), "SanitizerTest"], check=True, timeout=60)
