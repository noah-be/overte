#!/usr/bin/env python3
"""Compile and execute the real shared HTML surface policy with installed Qt."""
from pathlib import Path
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[4]
module = next((name for name in ("Qt6Core", "Qt5Core")
               if subprocess.run(["pkg-config", "--exists", name], check=False).returncode == 0), None)
if module is None:
    raise SystemExit("Install Qt Core development files to run the embedded web policy host check")
flags = shlex.split(subprocess.check_output(["pkg-config", "--cflags", "--libs", module], text=True))
flags = [part for flag in flags for part in
         (["-isystem", flag[2:]] if flag.startswith("-I") else [flag])]
with tempfile.TemporaryDirectory(prefix="overte-embedded-web-policy-") as scratch:
    binary = str(Path(scratch) / "policy-test")
    subprocess.run(["c++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-fPIC", "-pthread",
                    str(Path(__file__).with_name("embedded-web-policy-test.cpp")),
                    "-o", binary, *flags], check=True, timeout=90)
    subprocess.run([binary], check=True, timeout=15)
