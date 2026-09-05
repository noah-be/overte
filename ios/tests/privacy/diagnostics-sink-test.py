#!/usr/bin/env python3
"""Run production native sink and Qt startup installer with OS transport captured."""
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path
ios = Path(__file__).resolve().parents[2]
flags = shlex.split(subprocess.check_output(["pkg-config", "--cflags", "--libs", "Qt6Core"], text=True, timeout=10))
# Qt headers are external dependencies, not sources under this focused -Werror check.
flags = [part for flag in flags for part in (["-isystem", flag[2:]] if flag.startswith("-I") else [flag])]
with tempfile.TemporaryDirectory(prefix="overte-ios-px16-") as scratch:
    binary = str(Path(scratch) / "test")
    subprocess.run([shutil.which("clang++") or "c++", "-x", "c++", "-std=c++17",
                    "-Wall", "-Wextra", "-Werror", "-fPIC",
                    "-I" + str(ios / "tests/privacy/stubs"),
                    str(ios / "src/RedactingDiagnostics.mm"),
                    str(ios / "diagnostics/InstallSafeQtLogging.cpp"),
                    str(Path(__file__).with_suffix(".cpp")), "-o", binary, *flags], check=True, timeout=60)
    subprocess.run([binary], check=True, timeout=10)
print("PASS actual PX-16 native sink and pre-application Qt handler with captured OS transport")
